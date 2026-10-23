"""Two invocations per command. <= 2 seconds: next; > 2 seconds: previous.

The first invocation exits after saving its start time. There is no waiting
shortcut to block the second Action Button invocation. State is consumed before
the media command. A pending first invocation has no expiry.
"""
from pathlib import Path
import argparse
import plistlib
import subprocess
import uuid

ROOT = Path(__file__).resolve().parent


def workflow(actions):
    return {
        'WFWorkflowClientVersion': '3036.0.4',
        'WFWorkflowMinimumClientVersion': 900,
        'WFWorkflowMinimumClientVersionString': '900',
        'WFWorkflowIcon': {'WFWorkflowIconStartColor': 4282601983,
                           'WFWorkflowIconGlyphNumber': 61440},
        'WFWorkflowTypes': [],
        'WFWorkflowInputContentItemClasses': [],
        'WFWorkflowActions': actions,
    }


def build(diagnostic=False):
    actions = []
    state_path = ('ActionMusicInterval-test.txt' if diagnostic
                  else 'ActionMusicInterval.txt')

    def add(kind, **params):
        uid = str(uuid.uuid4()).upper()
        params['UUID'] = uid
        actions.append({'WFWorkflowActionIdentifier': 'is.workflow.actions.' + kind,
                        'WFWorkflowActionParameters': params})
        return uid

    def ref(uid):
        return {'Value': {'Type': 'ActionOutput', 'OutputUUID': uid,
                          'OutputName': 'Result'},
                'WFSerializationType': 'WFTextTokenAttachment'}

    def text_ref(uid):
        return {'Value': {'string': '\ufffc',
                          'attachmentsByRange': {'{0, 1}': ref(uid)['Value']}},
                'WFSerializationType': 'WFTextTokenString'}

    def condition(uid, code, **operand):
        group = str(uuid.uuid4()).upper()
        add('conditional', GroupingIdentifier=group, WFControlFlowMode=0,
            WFInput={'Type': 'Variable', 'Variable': ref(uid)},
            WFCondition=code, **operand)
        return group

    def flow(group, mode):
        add('conditional', GroupingIdentifier=group, WFControlFlowMode=mode)

    def save(uid):
        add('documentpicker.save', WFInput=ref(uid),
            WFFileStorageService='iCloud Drive', WFAskWhereToSave=False,
            WFFileDestinationPath=state_path, WFSaveFileOverwrite=True)

    def finish(label):
        if diagnostic:
            uid = add('gettext', WFTextActionText=label)
            add('documentpicker.save', WFInput=ref(uid),
                WFFileStorageService='iCloud Drive', WFAskWhereToSave=False,
                WFFileDestinationPath='ActionMusicInterval-result.txt',
                WFSaveFileOverwrite=True)
        add('nothing')
        add('exit')

    # Capture entry time before storage I/O.
    now = add('date', WFDateActionMode='Current Date')
    state = add('documentpicker.open', WFFileStorageService='iCloud Drive',
                WFShowFilePicker=False, WFGetFilePath=state_path,
                WFFileErrorIfNotFound=False)

    def arm():
        timestamp = add('format.date', WFDate=text_ref(now), WFDateFormatStyle='Custom',
                        WFDateFormat="yyyy-MM-dd'T'HH:mm:ss.SSSXXX")
        save(timestamp)
        finish('armed')

    missing = condition(state, 101)
    arm()
    flow(missing, 2)
    content = add('gettext', WFTextActionText=text_ref(state))
    idle = condition(content, 4, WFConditionalActionString='idle')
    arm()
    flow(idle, 2)
    previous = add('detect.date', WFInput=ref(content))
    delta = add('gettimebetweendates', WFInput=text_ref(now),
                WFTimeUntilFromDate=text_ref(previous),
                WFTimeUntilUnit='Seconds')
    # Consume pending state before sending a media command.
    cleared = add('gettext', WFTextActionText='idle')
    save(cleared)
    backward_clock = condition(delta, 0, WFNumberValue=0)
    arm()
    flow(backward_clock, 2)
    slower = condition(delta, 2, WFNumberValue=2)
    if not diagnostic:
        add('seek', WFSeekBehavior='To Time', WFTimeInterval={
            'Value': {'Magnitude': '0', 'Unit': 'sec'},
            'WFSerializationType': 'WFQuantityFieldValue'})
        add('skipback', WFSkipBackBehavior='Beginning')
    finish('previous')
    flow(slower, 1)
    if not diagnostic:
        add('skipforward')
    finish('next')
    flow(slower, 2)
    return actions


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--unsigned', action='store_true',
                        help='Only generate the inspectable source plist')
    parser.add_argument('--diagnostic', action='store_true',
                        help='Record branch names to separate test files; do not control music')
    parser.add_argument('--output-dir', type=Path, default=ROOT / 'build')
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    name = 'IntervalDiagnostic' if args.diagnostic else '操作按钮两秒切歌'
    source = args.output_dir / (name + '.source.shortcut')
    target = args.output_dir / (name + '.shortcut')
    source.write_bytes(plistlib.dumps(workflow(build(args.diagnostic))))
    if not args.unsigned:
        subprocess.run(['shortcuts', 'sign', '--mode', 'anyone',
                        '--input', str(source), '--output', str(target)], check=True)
    print(source if args.unsigned else target)
