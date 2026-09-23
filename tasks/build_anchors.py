"""Reproduce the three offline task payloads; never runs the benchmark."""
import ast
import difflib
import hashlib
import json
from pathlib import Path
import re
import textwrap

ROOT = Path(__file__).resolve().parent
UP = ROOT / 'upstream'
EVIDENCE = ROOT / '.evidence'


def clean(text):
    return textwrap.dedent(text).lstrip('\n')


class StripDocs(ast.NodeTransformer):
    def visit_Expr(self, node):
        if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            return None
        return self.generic_visit(node)


class Rename(ast.NodeTransformer):
    def __init__(self, names, strings):
        self.names = names
        self.strings = strings

    def visit_Name(self, node):
        node.id = self.names.get(node.id, node.id)
        return node

    def visit_arg(self, node):
        node.arg = self.names.get(node.arg, node.arg)
        return self.generic_visit(node)

    def visit_Attribute(self, node):
        node.attr = self.names.get(node.attr, node.attr)
        return self.generic_visit(node)

    def visit_keyword(self, node):
        node.arg = self.names.get(node.arg, node.arg)
        return self.generic_visit(node)

    def visit_FunctionDef(self, node):
        node.name = self.names.get(node.name, node.name)
        return self.generic_visit(node)

    visit_ClassDef = visit_FunctionDef

    def visit_alias(self, node):
        # Preserve standard-library symbols (notably typing.Pattern).
        if node.name in ('Binding', 'parse_stream', 'RegexPattern'):
            node.name = self.names.get(node.name, node.name)
        if node.asname:
            node.asname = self.names.get(node.asname, node.asname)
        return node

    def visit_Constant(self, node):
        if isinstance(node.value, str):
            node.value = self.strings.get(node.value, node.value)
        return node


def emit(source, names, strings):
    tree = StripDocs().visit(ast.parse(source))
    tree = Rename(names, strings).visit(tree)
    ast.fix_missing_locations(tree)
    result = ast.unparse(tree) + '\n'
    # Formatting must preserve the complete transformed executable tree.
    assert ast.dump(ast.parse(result)) == ast.dump(tree)
    return result


def definitions(source, selected):
    tree = ast.parse(source)
    tree.body = [n for n in tree.body if getattr(n, 'name', None) in selected]
    assert {n.name for n in tree.body} == set(selected)
    return ast.unparse(tree) + '\n'


RULE_NAMES = {
    'Pattern': 'RuleBase', 'RegexPattern': 'TextRule', 'RegexMatchResult': 'Hit',
    'PatternHint': 'CompiledHint', 'MatchHint': 'HitHint',
    'include': 'decision', 'pattern': 'expression', 'regex': 'compiled',
    'match_file': 'match_path', 'pattern_to_regex': 'compile_text',
    'files': 'paths', 'file': 'path', 'other': 'candidate',
}
RULE_STRINGS = {
    **{k: RULE_NAMES[k] for k in ('include', 'pattern', 'regex', 'RegexPattern', 'RegexMatchResult')},
    'include:': 'decision ', ' must be null when pattern:': ' requires no override for expression ',
    ' is a string.': ' supplied as text.', ' is null.': ' supplied as disabled.',
    'pattern:': 'expression ', ' is not a string, re.Pattern, or None.': ' must be text, a compiled matcher, or disabled.',
    '{cls.__module__}.{cls.__qualname__} must override match_file().':
        '{cls.__module__}.{cls.__qualname__} needs a match_path implementation.',
    '{cls.__module__}.{cls.__qualname__}.match() is deprecated. Use {cls.__module__}.{cls.__qualname__}.match_file() with a loop for similar results.':
        '{cls.__module__}.{cls.__qualname__}.match() is legacy; iterate using match_path().',
}
LEX_NAMES = {
    'make_regex': 'compile_token', '_newline': '_line_break',
    '_multiline_whitespace': '_record_space', '_whitespace': '_inline_space',
    '_export': '_prefix_token', '_single_quoted_key': '_quoted_name',
    '_unquoted_key': '_bare_name', '_equal_sign': '_assignment_token',
    '_single_quoted_value': '_single_value', '_double_quoted_value': '_double_value',
    '_unquoted_value': '_bare_value', '_comment': '_comment_token',
    '_end_of_line': '_record_end', '_rest_of_line': '_discard_tail',
    '_double_quote_escapes': '_double_escapes', '_single_quote_escapes': '_single_escapes',
    'Original': 'SourceText', 'Binding': 'Record', 'Position': 'Cursor',
    'Error': 'ScanError', 'Reader': 'Scanner', 'string': 'text',
    'key': 'name', 'original': 'source_text', 'error': 'invalid',
    'chars': 'offset', 'position': 'cursor', 'mark': 'checkpoint',
    'has_next': 'has_more', 'set_mark': 'remember', 'get_marked': 'remembered',
    'read_regex': 'consume', 'decode_escapes': 'unescape', 'decode_match': 'unescape_hit',
    'parse_key': 'scan_name', 'parse_unquoted_value': 'scan_bare_value',
    'parse_value': 'scan_value', 'parse_binding': 'scan_record',
    'parse_stream': 'scan_records', 'reader': 'scanner',
}
LEX_STRINGS = {
    **{k: LEX_NAMES[k] for k in ('Original', 'Binding', 'Position', 'string', 'key', 'original', 'error')},
    'read: End of string': 'The record ended before the requested text.',
    'read_regex: Pattern not found': 'The next token did not match.',
}
EDIT_NAMES = {
    **{k: LEX_NAMES[k] for k in ('Binding', 'parse_stream', 'key', 'original', 'string', 'error')},
    'with_warn_for_invalid_lines': 'report_invalid_records',
    'mappings': 'records', 'mapping': 'record', 'rewrite': 'staged_edit',
    'set_key': 'store_value', 'dotenv_path': 'settings_path',
    'key_to_set': 'name_to_store', 'value_to_set': 'text_to_store',
    'quote_mode': 'quote_style', 'export': 'export_entry', 'quote': 'use_quotes',
    'value_out': 'encoded_value', 'line_out': 'new_record', 'replaced': 'updated',
    'missing_newline': 'needs_separator', '_PathLike': '_FilePath', 'logger': 'log',
    'source': 'incoming', 'dest': 'outgoing',
}
EDIT_STRINGS = {
    'Python-dotenv could not parse statement starting at line %s': 'Unrecognized settings record at line %s',
    'Unknown quote_mode: {}': 'Unsupported quoting style: {}',
}
GLOB_NAMES = {
    **RULE_NAMES, 'GitWildMatchPattern': 'PathRule', 'GitWildMatchPatternError': 'RuleSyntaxError',
    '_BYTES_ENCODING': '_TEXT_CODEC', '_DIR_MARK': '_DIRECTORY_GROUP',
    'original_pattern': 'original_expression', 'pattern_segs': 'pieces',
    'override_regex': 'special_expression', 'is_dir_pattern': 'directory_only',
    '_translate_segment_glob': '_compile_piece', 'need_slash': 'needs_separator',
    'return_type': 'output_type', 'out_string': 'escaped_text',
    'meta_characters': 'special_characters',
}
GLOB_STRINGS = {
    'ps_d': 'directory_edge', 'pattern:': 'expression ',
    ' is not a unicode or byte string.': ' must be text or bytes.',
    'Invalid git pattern: ': 'Malformed path rule: ',
    'Escape character found with no next character to escape: ': 'Dangling escape in path rule: ',
    's:': 'input ',
}


def make_sources():
    old_main = (UP / 'dotenv-main-v0.19.1-prefix.py').read_text()
    new_main = (UP / 'dotenv-main-v0.19.2-fixed.py').read_text()
    header = '''import io
import logging
import os
import shutil
import sys
import tempfile
from contextlib import contextmanager
from typing import IO, Iterator, Optional, Tuple, Union
from .records import Binding, parse_stream
logger = logging.getLogger(__name__)
if sys.version_info >= (3, 6):
    _PathLike = os.PathLike
else:
    _PathLike = str
'''
    selected = ('with_warn_for_invalid_lines', 'rewrite', 'set_key')
    old_editor = header + definitions(old_main, selected)
    new_editor = header + definitions(new_main, selected)
    lexer = (UP / 'dotenv-parser-v0.19.2.py').read_text()
    rule_old = (UP / 'pathspec-pattern-v0.12.1-prefix.py').read_text()
    # Isolate the #98 executable change, omitting unrelated typing modernization.
    rule_new = rule_old.replace(
        '\t\t\t\tf"include:{include!r} must be null when pattern:{pattern!r} is null."\n\t\t\t)',
        '\t\t\t\tf"include:{include!r} must be null when pattern:{pattern!r} is null."\n\t\t\t)\n\t\t\tregex = None',
    )
    assert rule_new != rule_old
    upstream_rule_new = (UP / 'pathspec-pattern-v1.0.0-fixed.py').read_text()
    assert 'is null."\n\t\t\t)\n\t\t\tregex = None' in upstream_rule_new
    glob_full = (UP / 'pathspec-gitwildmatch-v0.12.1.py').read_text()
    glob_header = '''import re
from typing import AnyStr, Optional, Tuple
from .rules import RegexPattern
_BYTES_ENCODING = 'latin1'
_DIR_MARK = 'ps_d'
'''
    glob_old = glob_header + definitions(glob_full, ('GitWildMatchPatternError', 'GitWildMatchPattern'))
    # Apply the #93 normalization block from the new basic/spec modules.
    glob_new = glob_old.replace('pattern = pattern.lstrip()', 'pass').replace(
        'pattern = pattern.strip()', 'pattern = pattern.rstrip()')
    assert glob_new != glob_old
    release_diff = (UP / 'pathspec-v0.12.1..v1.0.0.diff').read_text()
    assert '+\t\t\tpattern_str = pattern_str.rstrip()' in release_diff
    return {
        'editor': (emit(old_editor, EDIT_NAMES, EDIT_STRINGS), emit(new_editor, EDIT_NAMES, EDIT_STRINGS)),
        'records': emit(lexer, LEX_NAMES, LEX_STRINGS),
        'rules': (emit(rule_old, RULE_NAMES, RULE_STRINGS), emit(rule_new, RULE_NAMES, RULE_STRINGS)),
        'globs': (emit(glob_old, GLOB_NAMES, GLOB_STRINGS), emit(glob_new, GLOB_NAMES, GLOB_STRINGS)),
        'raw_pairs': {'append-setting': (old_editor, new_editor),
                      'disabled-rule': (rule_old, rule_new),
                      'literal-leading-space': (glob_old, glob_new)},
    }


SETTING_TEST = clean(r'''
    import contextlib
    import io
    from pathlib import Path
    import tempfile
    import unittest
    from main import main
    from settings.editor import store_value
    from settings.records import scan_records

    class SettingsRegression(unittest.TestCase):
        def test_append_boundaries(self):
            for prefix in ('', 'COLOR=blue', 'COLOR=blue\n', '# keep this note',
                           '# keep this note\n', 'COLOR=blue\n# final note',
                           'TEXT="first\nsecond"', 'FLAG', '  ',
                           'COLOR=blue\n\n', 'BROKEN="unfinished'):
                for style, value, rendered in (('never', 'oak', 'oak'),
                                                ('always', 'two words', "'two words'"),
                                                ('auto', 'plain7', 'plain7'),
                                                ('auto', "oak's", "'oak\\'s'")):
                    for exported in (False, True):
                        with self.subTest(prefix=prefix, style=style, exported=exported):
                            with tempfile.TemporaryDirectory() as folder:
                                path = Path(folder) / 'settings.txt'
                                path.write_text(prefix, encoding='utf-8')
                                outcome = store_value(path, 'NEW', value, quote_style=style, export_entry=exported)
                                separator = '\n' if prefix and not prefix.endswith('\n') else ''
                                addition = ('export ' if exported else '') + 'NEW=' + rendered + '\n'
                                self.assertEqual(path.read_text(), prefix + separator + addition)
                                self.assertEqual(outcome, (True, 'NEW', value))
                                rows = list(scan_records(io.StringIO(path.read_text())))
                                self.assertEqual([(r.name, r.value) for r in rows if r.name == 'NEW'], [('NEW', value)])

        def test_update_does_not_append_or_repair_unrelated_tail(self):
            for before, after in (
                ('MODE=old', 'MODE=new\n'),
                ('MODE=old\nTAIL=x', 'MODE=new\nTAIL=x'),
                ('HEAD=x\nMODE=old', 'HEAD=x\nMODE=new\n'),
                ('MODE=a\nMODE=b\n# footer', 'MODE=new\nMODE=new\n# footer'),
            ):
                with self.subTest(before=before), tempfile.TemporaryDirectory() as folder:
                    path = Path(folder) / 'settings.txt'
                    path.write_text(before)
                    store_value(path, 'MODE', 'new', quote_style='never')
                    self.assertEqual(path.read_text(), after)

        def test_lengths_and_consecutive_appends(self):
            for size in (0, 1, 63, 257, 4097):
                with self.subTest(size=size), tempfile.TemporaryDirectory() as folder:
                    path = Path(folder) / 'settings.txt'
                    before = 'PAYLOAD=' + 'x' * size
                    path.write_text(before)
                    for name in ('NEXT', 'LAST'):
                        store_value(path, name, 'ok', quote_style='never')
                    self.assertEqual(path.read_text(), before + '\nNEXT=ok\nLAST=ok\n')

        def test_cli_and_rejected_option(self):
            with tempfile.TemporaryDirectory() as folder:
                path = Path(folder) / 'settings.txt'
                path.write_text('COLOR=blue')
                self.assertEqual(main([str(path), 'SIZE', 'large', '--quote-style', 'never']), 0)
                self.assertEqual(path.read_text(), 'COLOR=blue\nSIZE=large\n')
                before = path.read_bytes()
                with self.assertRaises(ValueError):
                    store_value(path, 'SIZE', 'small', quote_style='invalid')
                self.assertEqual(path.read_bytes(), before)
                with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as caught:
                    main([str(path), 'SIZE', 'small', '--quote-style', 'invalid'])
                self.assertEqual(caught.exception.code, 2)
                self.assertEqual(path.read_bytes(), before)

    if __name__ == '__main__':
        unittest.main()
''')

RULE_TEST = clean(r'''
    import contextlib
    import io
    import json
    import re
    import unittest
    from main import main
    from routing.rules import TextRule

    class RuleRegression(unittest.TestCase):
        def test_disabled_construction_and_matching(self):
            for factory in (lambda: TextRule(None), lambda: TextRule(expression=None),
                            lambda: TextRule(None, decision=None)):
                with self.subTest(factory=factory):
                    rule = factory()
                    self.assertIsNone(rule.expression)
                    self.assertIsNone(rule.decision)
                    self.assertIsNone(rule.compiled)
                    for path in ('', 'note.txt', 'folder/note.txt', b'', b'note.txt'):
                        self.assertIsNone(rule.match_path(path))
                    self.assertEqual(rule, TextRule(None))

        def test_active_and_compiled_rules_still_work(self):
            for expression, yes, no in ((r'^docs/.*\.txt$', 'docs/a.txt', 'docs/a.bin'),
                                         (br'^img/.*\.png$', b'img/a.png', b'img/a.jpg')):
                with self.subTest(expression=expression):
                    rule = TextRule(expression)
                    self.assertIs(rule.decision, True)
                    self.assertIsNotNone(rule.match_path(yes))
                    self.assertIsNone(rule.match_path(no))
                    compiled = re.compile(expression)
                    for decision in (True, False, None):
                        with self.subTest(decision=decision):
                            rule = TextRule(compiled, decision=decision)
                            self.assertIs(rule.decision, decision)
                            self.assertEqual(rule.match_path(yes) is not None, decision is not None)
                            self.assertIsNone(rule.match_path(no))

        def test_instance_order_and_subclasses(self):
            class QuietRule(TextRule):
                @classmethod
                def compile_text(cls, expression):
                    return None, None

            for entries in ((None, '^a', '^z', None), ('^z', None, '^a', None)):
                with self.subTest(entries=entries):
                    rules = [TextRule(entry) for entry in entries]
                    self.assertEqual([r.match_path('apple') is not None for r in rules],
                                     [entry == '^a' for entry in entries])
            for expression in (None, '', 'anything', b'anything'):
                with self.subTest(expression=expression):
                    quiet = QuietRule(expression)
                    self.assertIsNone(quiet.match_path('apple'))
            self.assertNotEqual(TextRule(None), TextRule(''))
            self.assertNotEqual(TextRule(None), object())
            self.assertIsNotNone(TextRule('').match_path(''))

        def test_invalid_arguments_remain_invalid(self):
            for decision in (True, False):
                with self.subTest(decision=decision):
                    with self.assertRaises(AssertionError):
                        TextRule(None, decision=decision)
                    with self.assertRaises(AssertionError):
                        TextRule('x', decision=decision)
            for bad in (13, object(), [], {}):
                with self.subTest(bad=type(bad).__name__), self.assertRaises(TypeError):
                    TextRule(bad)

        def test_cli_with_optional_rule_and_bad_input(self):
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                self.assertEqual(main(['--rules', '[null, "^docs/", null]', 'docs/a', 'tmp/a']), 0)
            self.assertEqual(json.loads(output.getvalue()), [[False, True, False], [False, False, False]])
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as caught:
                main(['--rules', '{', 'docs/a'])
            self.assertEqual(caught.exception.code, 2)

    if __name__ == '__main__':
        unittest.main()
''')

GLOB_TEST = clean(r'''
    import contextlib
    import io
    import json
    import unittest
    from main import main
    from selection.globs import PathRule

    class LeadingSpaceRegression(unittest.TestCase):
        def check_rule(self, expression, yes, no):
            for as_bytes in (False, True):
                convert = (lambda value: value.encode('latin1')) if as_bytes else (lambda value: value)
                with self.subTest(expression=expression, as_bytes=as_bytes):
                    rule = PathRule(convert(expression))
                    for path in yes:
                        with self.subTest(path=path):
                            self.assertIsNotNone(rule.match_path(convert(path)))
                    for path in no:
                        with self.subTest(path=path):
                            self.assertIsNone(rule.match_path(convert(path)))

        def test_leading_spaces_at_several_depths(self):
            for count in (1, 2, 4):
                for label in ('memo', 'report-27', 'x' * 129):
                    prefix = ' ' * count
                    self.check_rule(prefix + label,
                                    [prefix + label, 'box/' + prefix + label, prefix + label + '/child'],
                                    [label, 'box/' + label, ' ' * (count + 1) + label])
            self.check_rule(' */report?.[ch]', [' folder/report1.c', ' x/report2.h'],
                            ['folder/report1.c', 'box/ folder/report1.c', ' x/report22.h'])
            self.check_rule(' cache/', [' cache/a', 'box/ cache/deep/a'], ['cache/a', ' cache'])

        def test_trailing_and_escaped_spaces(self):
            self.check_rule(' note  ', [' note', 'box/ note'], ['note', ' note  '])
            self.check_rule('  note\\ ', ['  note ', 'box/  note '], ['note ', '  note', ' note '])
            self.check_rule('plain  ', ['plain', 'box/plain'], ['plain  ', ' plain'])
            self.check_rule('\\ note', [' note'], ['note'])

        def test_leading_space_changes_control_character_meaning(self):
            self.check_rule(' #draft', [' #draft', 'box/ #draft'], ['#draft', 'draft'])
            self.check_rule(' !draft', [' !draft', 'box/ !draft'], ['!draft', 'draft'])
            self.check_rule('! draft', [' draft', 'box/ draft'], ['draft'])
            self.assertIs(PathRule('! draft').decision, False)
            self.assertIs(PathRule(' !draft').decision, True)
            for expression in ('', ' ', '    ', '#draft', '/'):
                with self.subTest(expression=expression):
                    self.assertIsNone(PathRule(expression).match_path('draft'))
            self.check_rule('*.txt', ['a.txt', 'box/a.txt'], ['a.bin'])
            self.check_rule('/root.txt', ['root.txt'], ['box/root.txt'])

        def test_cli_and_invalid_expression(self):
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                self.assertEqual(main([' note', 'note', ' note', 'box/ note']), 0)
            self.assertEqual(json.loads(output.getvalue()), [False, True, True])
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as caught:
                main(['broken\\', 'anything'])
            self.assertEqual(caught.exception.code, 2)
            with self.assertRaises(TypeError):
                PathRule(17)

    if __name__ == '__main__':
        unittest.main()
''')


def make_tasks(sources):
    settings_cli = clean('''
        import argparse
        from settings.editor import store_value

        def main(argv=None):
            parser = argparse.ArgumentParser(description='Store a settings value.')
            parser.add_argument('path')
            parser.add_argument('name')
            parser.add_argument('value')
            parser.add_argument('--quote-style', choices=('always', 'auto', 'never'), default='always')
            parser.add_argument('--export-entry', action='store_true')
            args = parser.parse_args(argv)
            store_value(args.path, args.name, args.value, args.quote_style, args.export_entry)
            return 0

        if __name__ == '__main__':
            raise SystemExit(main())
    ''')
    rules_cli = clean('''
        import argparse
        import json
        import re
        from routing.rules import TextRule

        def main(argv=None):
            parser = argparse.ArgumentParser(description='Check paths against optional routing rules.')
            parser.add_argument('--rules', required=True, help='JSON array of strings or null')
            parser.add_argument('paths', nargs='+')
            args = parser.parse_args(argv)
            try:
                expressions = json.loads(args.rules)
                if not isinstance(expressions, list) or any(x is not None and not isinstance(x, str) for x in expressions):
                    raise ValueError('Expected a list of text or null entries.')
                rules = [TextRule(x) for x in expressions]
            except (ValueError, TypeError, re.error) as error:
                parser.error(str(error))
            print(json.dumps([[r.match_path(p) is not None for r in rules] for p in args.paths]))
            return 0

        if __name__ == '__main__':
            raise SystemExit(main())
    ''')
    globs_cli = clean('''
        import argparse
        import json
        from selection.globs import PathRule

        def main(argv=None):
            parser = argparse.ArgumentParser(description='Check a selection expression against paths.')
            parser.add_argument('expression')
            parser.add_argument('paths', nargs='+')
            args = parser.parse_args(argv)
            try:
                rule = PathRule(args.expression)
            except (ValueError, TypeError) as error:
                parser.error(str(error))
            print(json.dumps([rule.match_path(path) is not None for path in args.paths]))
            return 0

        if __name__ == '__main__':
            raise SystemExit(main())
    ''')
    return [
        {
            'id': 'append-setting', 'kind': 'unittest', 'group': 'anchor',
            'prompt': 'Adding a setting to a file without a final newline corrupts its last record. Fix the editor using README.md as the contract. Keep existing quoting and update behavior.',
            'files': {
                'README.md': clean('''
                    # Settings editor

                    I sometimes edit our shop's settings by hand and leave off the final newline.
                    Adding SIZE=large to a file containing COLOR=blue then glues both assignments
                    together. A trailing comment can swallow the added setting too.

                    Fix store_value in settings/editor.py so appending an absent name puts the new
                    assignment on its own line. Keep all existing text, including comments, blank
                    lines, malformed records and multiline quoted values. Add exactly one separating
                    newline only when nonempty preserved text has no final newline. An empty file
                    must not acquire a leading blank line. The new assignment ends with a newline.

                    Updating a name already present replaces each occurrence in place; it must not
                    append another occurrence or normalize unrelated trailing text. Keep the return
                    tuple (True, name, original_value). Quoting styles are always, auto (quote values
                    that are not alphanumeric), and never. Quoted values use single quotes and escape
                    embedded single quotes. export_entry adds the literal 'export ' prefix.
                    An unsupported quoting style raises ValueError without changing the file.

                    Run: python3 main.py settings.txt SIZE large --quote-style never
                    Only the Python standard library is needed. File contents are UTF-8 text.
                '''),
                'settings/__init__.py': '"""Settings file editing utilities."""\n',
                'settings/records.py': sources['records'],
                'settings/editor.py': sources['editor'][0],
                'main.py': settings_cli,
            },
            'hidden_tests': {'test_hidden.py': SETTING_TEST},
            'reference_files': {'settings/editor.py': sources['editor'][1]},
        },
        {
            'id': 'disabled-rule', 'kind': 'unittest', 'group': 'anchor',
            'prompt': 'A disabled optional routing rule crashes during construction. Repair the rule implementation to satisfy README.md without breaking active or precompiled rules.',
            'files': {
                'README.md': clean('''
                    # Optional routing rules

                    Some routing slots are disabled. Passing None for such a slot should construct
                    an inert TextRule, but construction currently crashes before I can check any path.

                    TextRule(expression, decision=None) accepts a text/bytes regular expression,
                    a precompiled matcher, or None. None with decision=None is an inert rule: its
                    public expression, compiled and decision attributes are None, and match_path
                    returns None for every text or bytes path. Two such rules compare equal.
                    An empty expression is an active regex and can match an empty path.

                    Text and bytes expressions compile as active rules (decision=True); passing
                    an explicit boolean decision with either text or None remains an AssertionError.
                    A precompiled matcher accepts True, False or None: both booleans allow matches,
                    preserving the decision, while None disables matching. A match returns a Hit
                    containing the match object; a miss returns None. Other expression types raise
                    TypeError. Subclasses may override compile_text to return (None, None).
                    Instances must remain independent, including when active and disabled rules mix.

                    Run: python3 main.py --rules '[null, "^docs/"]' docs/a tmp/a
                    The JSON result has one row per path and one boolean per rule, in input order.
                    Invalid CLI input exits with status 2. Only the standard library is needed.
                '''),
                'routing/__init__.py': '"""Optional routing matchers."""\n',
                'routing/rules.py': sources['rules'][0],
                'main.py': rules_cli,
            },
            'hidden_tests': {'test_hidden.py': RULE_TEST},
            'reference_files': {'routing/rules.py': sources['rules'][1]},
        },
        {
            'id': 'literal-leading-space', 'kind': 'unittest', 'group': 'anchor',
            'prompt': 'Selection rules accidentally match names without their leading spaces. Fix whitespace handling in the existing matcher according to README.md, preserving its other matching behavior.',
            'files': {
                'README.md': clean(r'''
                    # File selection rules

                    Our archive includes filenames starting with spaces. The expression ' memo'
                    should select ' memo' and 'box/ memo', but currently acts like 'memo'.
                    Leading spaces in a selection expression are literal characters, even when
                    there are several, or the next character is #, ! or a wildcard.

                    PathRule accepts text or bytes expressions and match_path accepts corresponding
                    text or bytes paths. It returns a Hit when matching and None otherwise. Expressions
                    without an embedded slash match at any depth; a leading slash anchors at the root.
                    A trailing slash selects directories and their descendants, not a bare file.
                    Keep *, **, ?, bracket sets, and backslash escaping working.

                    Unescaped trailing whitespace is ignored. If the expression ends in a backslash
                    followed by a space, preserve that escaped final space AND all leading spaces.
                    For example, '  note\ ' selects '  note ' but not 'note ' or '  note'.
                    A # at column zero starts a comment; an ! at column zero makes decision=False
                    while keeping the usual match result. A space before either makes it literal.
                    Empty/all-space rules and a solitary slash match nothing. Trailing backslash
                    without a character is invalid and raises ValueError. Other input types raise
                    TypeError. Do not change unrelated matching rules.

                    Run: python3 main.py ' memo' memo ' memo' 'box/ memo'
                    Output is a JSON list of matching booleans, in path order. Invalid expressions
                    exit with status 2. Only the standard library is needed.
                '''),
                'selection/__init__.py': '"""Archive path selection."""\n',
                'selection/rules.py': sources['rules'][0],
                'selection/globs.py': sources['globs'][0],
                'main.py': globs_cli,
            },
            'hidden_tests': {'test_hidden.py': GLOB_TEST},
            'reference_files': {'selection/globs.py': sources['globs'][1]},
        },
    ]


def main():
    sources = make_sources()
    tasks = make_tasks(sources)
    maps = {
        'settings/records.py': {'identifiers': LEX_NAMES, 'strings': LEX_STRINGS},
        'settings/editor.py': {'identifiers': EDIT_NAMES, 'strings': EDIT_STRINGS},
        'routing/rules.py and selection/rules.py': {'identifiers': RULE_NAMES, 'strings': RULE_STRINGS},
        'selection/globs.py': {'identifiers': GLOB_NAMES, 'strings': GLOB_STRINGS},
    }
    (EVIDENCE / 'rename-map.json').write_text(json.dumps(maps, indent=2) + '\n')
    for task in tasks:
        payload = json.dumps(task, indent=2, ensure_ascii=False) + '\n'
        assert len(payload.encode()) < 40_000
        (ROOT / (task['id'] + '.json')).write_text(payload)
        old, new = sources['raw_pairs'][task['id']]
        patch = ''.join(difflib.unified_diff(old.splitlines(True), new.splitlines(True),
                                            fromfile='pre-fix-extract.py', tofile='fixed-extract.py'))
        (EVIDENCE / (task['id'] + '-upstream.patch')).write_text(patch)
        for name, fixed in task['reference_files'].items():
            patch = ''.join(difflib.unified_diff(task['files'][name].splitlines(True), fixed.splitlines(True),
                                               fromfile='a/' + name, tofile='b/' + name))
            (EVIDENCE / (task['id'] + '-reference.patch')).write_text(patch)
        print(task['id'], len(payload.encode()), 'bytes')
    used = ['README.md', 'dotenv-main-v0.19.1-prefix.py', 'dotenv-main-v0.19.2-fixed.py',
            'dotenv-parser-v0.19.2.py', 'dotenv-v0.19.1..v0.19.2.diff', 'dotenv-LICENSE.txt',
            'pathspec-pattern-v0.12.1-prefix.py', 'pathspec-pattern-v1.0.0-fixed.py',
            'pathspec-gitwildmatch-v0.12.1.py', 'pathspec-gitwildmatch-v1.0.0-fixed.py',
            'pathspec-v0.12.1..v1.0.0.diff', 'pathspec-LICENSE.txt']
    (EVIDENCE / 'source-sha256.txt').write_text(''.join(
        hashlib.sha256((UP / name).read_bytes()).hexdigest() + '  upstream/' + name + '\n' for name in used))


if __name__ == '__main__':
    main()
