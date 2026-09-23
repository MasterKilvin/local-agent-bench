"""Local payload checks; no agent calls, network, or benchmark harness."""
import ast
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parent
EVIDENCE = ROOT / '.evidence'
IDS = ('append-setting', 'disabled-rule', 'literal-leading-space')
FIELDS = {'id', 'kind', 'group', 'prompt', 'files', 'hidden_tests', 'reference_files'}


def check_shape(task, payload):
    assert set(task) == FIELDS
    assert task['id'] in IDS
    assert task['kind'] == 'unittest' and task['group'] == 'anchor'
    assert 4 <= len(task['files']) <= 6
    assert 4 <= len(task['files'] | task['hidden_tests'] | task['reference_files']) <= 7
    assert len(payload) < 40_000
    assert len(task['reference_files']) == 1
    assert set(task['reference_files']) <= set(task['files'])
    assert not (set(task['hidden_tests']) & set(task['files']))
    assert not re.search(r'dotenv|pathspec|GitWildMatch|RegexPattern|github|/home/',
                         json.dumps(task), re.I)
    files = task['files'] | task['hidden_tests'] | task['reference_files']
    packages = {Path(name).parts[0] for name in files if '/' in name}
    for name, content in files.items():
        assert not Path(name).is_absolute() and '..' not in Path(name).parts
        if not name.endswith('.py'):
            continue
        tree = ast.parse(content)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules = [alias.name.split('.')[0] for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and not node.level:
                modules = [(node.module or '').split('.')[0]]
            else:
                continue
            assert all(module in sys.stdlib_module_names | packages | {'main'} for module in modules), modules
            assert not set(modules) & {'socket', 'urllib', 'http', 'requests', 'random', 'time'}


def run(task, variant, overrides):
    with tempfile.TemporaryDirectory(prefix=task['id'] + '-', dir=EVIDENCE) as scratch:
        folder = Path(scratch)
        for name, content in (task['files'] | overrides | task['hidden_tests']).items():
            target = folder / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding='utf-8')
        (folder / 'temp').mkdir()
        env = {**os.environ, 'PYTHONDONTWRITEBYTECODE': '1', 'PYTHONHASHSEED': '0',
               'PYTHONUTF8': '1', 'TMPDIR': str(folder / 'temp')}
        result = subprocess.run(
            [sys.executable, '-B', '-S', '-m', 'unittest', 'discover', '-s', '.', '-p', 'test_hidden.py', '-v'],
            cwd=folder, env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=20,
        )
    log = EVIDENCE / (task['id'] + '-' + variant + '.log')
    log.write_text(result.stdout)
    match = re.search(r'Ran (\d+) tests?', result.stdout)
    assert match, f'No tests ran: {log.name}'
    # A broken import or syntax error cannot count as reproducing the bug.
    assert 'Failed to import test module' not in result.stdout, log.name
    assert 'SyntaxError' not in result.stdout, log.name
    return {'exit_code': result.returncode, 'tests': int(match.group(1)), 'log': str(log.relative_to(ROOT))}


def mutant(task):
    name, fixed = next(iter(task['reference_files'].items()))
    if task['id'] == 'append-setting':
        # A common but incorrect repair adds a separator even to empty/terminated files.
        code = fixed.replace('if needs_separator:', 'if True:')
    elif task['id'] == 'disabled-rule':
        # Avoids the exception but accidentally treats the disabled rule as an empty regex.
        code = fixed.replace('compiled = None', "compiled = re.compile('')\n            decision = True")
    else:
        # Fixes ordinary leading spaces, but still strips them with an escaped trailing space.
        code = fixed.replace("if expression.endswith('\\\\ '):\n            pass",
                             "if expression.endswith('\\\\ '):\n            expression = expression.lstrip()")
    assert code != fixed, task['id']
    return {name: code}


def main():
    report = {'python': sys.version.split()[0], 'command': 'python3 -B verify_anchors.py', 'tasks': []}
    for task_id in IDS:
        payload = (ROOT / (task_id + '.json')).read_bytes()
        task = json.loads(payload)
        check_shape(task, payload)
        results = {
            'given': run(task, 'given', {}),
            'reference': run(task, 'reference', task['reference_files']),
            'incomplete_fix': run(task, 'incomplete-fix', mutant(task)),
        }
        passed = (results['given']['exit_code'] == 1 and results['reference']['exit_code'] == 0
                  and results['incomplete_fix']['exit_code'] == 1)
        report['tasks'].append({'id': task_id, 'bytes': len(payload),
                                'visible_files': len(task['files']),
                                'total_files_with_tests': len(task['files'] | task['hidden_tests']),
                                'sha256': hashlib.sha256(payload).hexdigest(),
                                'results': results, 'passed': passed})
        print(task_id, 'PASS' if passed else 'FAIL',
              ', '.join(f'{key}={value["exit_code"]}' for key, value in results.items()))
    (EVIDENCE / 'validation.json').write_text(json.dumps(report, indent=2) + '\n')
    assert all(row['passed'] for row in report['tasks']), 'See .evidence/*-reference.log'


if __name__ == '__main__':
    main()
