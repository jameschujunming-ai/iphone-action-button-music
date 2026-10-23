"""Packaging checks only; these do not simulate iOS or prove physical timing."""
import importlib.util
from pathlib import Path
import plistlib
import unittest

ROOT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('builder', ROOT / 'build_shortcut.py')
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


def normalized(actions):
    ids = {a['WFWorkflowActionParameters']['UUID']: f'action-{i}'
           for i, a in enumerate(actions)}
    groups = {}

    def walk(value):
        if isinstance(value, dict):
            result = {}
            for key, item in value.items():
                if key == 'GroupingIdentifier':
                    result[key] = groups.setdefault(item, f'group-{len(groups)}')
                else:
                    result[key] = walk(item)
            return result
        if isinstance(value, list):
            return [walk(v) for v in value]
        if isinstance(value, str):
            return ids.get(value, value)
        return value
    return walk(actions)


class ReleaseChecks(unittest.TestCase):
    def setUp(self):
        self.source = next(ROOT.glob('*.source.shortcut'))
        self.actions = plistlib.loads(self.source.read_bytes())['WFWorkflowActions']

    def test_builder_matches_shipped_source(self):
        self.assertEqual(normalized(self.actions), normalized(builder.build()))

    def test_no_volume_wait_or_display_actions_and_no_implicit_output(self):
        ids = [a['WFWorkflowActionIdentifier'].removeprefix('is.workflow.actions.')
               for a in self.actions]
        self.assertFalse(set(ids) & {'setvolume', 'getdevicedetails', 'delay',
                                    'alert', 'showresult', 'quicklook', 'ask',
                                    'choosefrommenu', 'output'})
        for i, action in enumerate(ids):
            if action == 'exit':
                self.assertEqual(ids[i - 1], 'nothing')

    def test_all_output_references_resolve(self):
        known = {a['WFWorkflowActionParameters']['UUID'] for a in self.actions}
        def walk(value):
            if isinstance(value, dict):
                if 'OutputUUID' in value:
                    self.assertIn(value['OutputUUID'], known)
                for item in value.values():
                    walk(item)
            elif isinstance(value, list):
                for item in value:
                    walk(item)
        walk(self.actions)

    def test_two_second_branch_and_media_commands_are_preserved(self):
        branch = next(a['WFWorkflowActionParameters'] for a in self.actions
                      if a['WFWorkflowActionIdentifier'].endswith('.conditional')
                      and a['WFWorkflowActionParameters'].get('WFNumberValue') == 2)
        self.assertEqual(branch['WFCondition'], 2)  # Greater than, not >=.
        ids = [a['WFWorkflowActionIdentifier'] for a in self.actions]
        self.assertEqual(ids.count('is.workflow.actions.skipforward'), 1)
        self.assertEqual(ids.count('is.workflow.actions.skipback'), 1)
        self.assertEqual(ids.count('is.workflow.actions.seek'), 1)


if __name__ == '__main__':
    unittest.main()
