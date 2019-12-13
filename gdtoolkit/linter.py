import re
from functools import partial
from types import MappingProxyType

from lark import Tree, Token

from .parser import parser_with_metadata_gathering

PASCAL_CASE_REGEX = r'([A-Z][a-z0-9]*)+'

DEFAULT_CONFIG = MappingProxyType({
    'function-name': r'(_on_[0-9a-zA-Z]+(_[a-z0-9]+)*|_?[a-z0-9]+(_[a-z0-9]+)*)',
    'function-arguments-number': 10,
    'class-name': PASCAL_CASE_REGEX,
    'sub-class-name': r'_?([A-Z][a-z0-9]*)+',
    'signal-name': r'[a-z][a-z0-9]*(_[a-z0-9]+)*',
    # TODO: class-variable-name
    # TODO: function-variable-name
    # TODO: function-argument-name
    # TODO: loop-variable-name (?)
    'enum-name': PASCAL_CASE_REGEX,
    # TODO: enum-value-name
    # TODO: constant-name
    'disable': [],
})


class Problem:                  # TODO: use dataclass if python 3.6 support is dropped
    def __init__(self, name: str, description: str, line: int, column: int):
        self.name = name
        self.description = description
        self.line = line
        self.column = column

    def __repr__(self):
        return 'Problem({})'.format({
            'name': self.name,
            'description': self.description,
            'line': self.line,
            'column': self.column,
        })


def lint_code(gdscript_code, config=DEFAULT_CONFIG):
    disable = config['disable']
    parse_tree = parser_with_metadata_gathering.parse(gdscript_code)
    rule_name_tokens = _gather_rule_name_tokens(parse_tree, [
        'class_def',
        'func_def',
        'classname_stmt',
        'signal_stmt',
        'enum_named',
    ])
    checks_to_run_w_tree = [
        (
            'function-arguments-number',
            partial(_function_args_num_check, config['function-arguments-number']),
        ),
    ]
    problem_clusters = map(
        lambda x: x[1](parse_tree) if x[0] not in disable else [], checks_to_run_w_tree
    )
    problems = [problem for cluster in problem_clusters for problem in cluster]
    checks_to_run_wo_tree = [
        (
            'function-name',
            partial(
                _generic_name_check,
                config['function-name'],
                rule_name_tokens['func_def'],
                'function-name',
                'Function name "{}" is not valid',
            ),
        ),
        (
            'sub-class-name',
            partial(
                _generic_name_check,
                config['sub-class-name'],
                rule_name_tokens['class_def'],
                'sub-class-name',
                'Class name "{}" is not valid',
            ),
        ),
        (
            'class-name',
            partial(
                _generic_name_check,
                config['class-name'],
                rule_name_tokens['classname_stmt'],
                'class-name',
                'Class name "{}" is not valid',
            ),
        ),
        (
            'signal-name',
            partial(
                _generic_name_check,
                config['signal-name'],
                rule_name_tokens['signal_stmt'],
                'signal-name',
                'Signal name "{}" is not valid',
            ),
        ),
        (
            'enum-name',
            partial(
                _generic_name_check,
                config['enum-name'],
                rule_name_tokens['enum_named'],
                'enum-name',
                'Enum name "{}" is not valid',
            ),
        ),
    ]
    problem_clusters = map(lambda x: x[1]() if x[0] not in disable else [], checks_to_run_wo_tree)
    problems += [problem for cluster in problem_clusters for problem in cluster]
    return problems


def _function_args_num_check(threshold, parse_tree):
    problems = []
    for func_def in parse_tree.find_data('func_def'):
        func_name_token = func_def.children[0]
        assert func_name_token.type == 'NAME'
        func_name = func_name_token.value
        if isinstance(func_def.children[1], Tree) and func_def.children[1].data == 'func_args':
            args_num = len(func_def.children[1].children)
            if args_num > threshold:
                problems.append(Problem(
                    name='function-arguments-number',
                    description='Function "{}" has more than {} arguments'.format(func_name, threshold),
                    line=func_name_token.line,
                    column=func_name_token.column,
                ))
    return problems


def _generic_name_check(name_regex, name_tokens, problem_name, description_template):
    problems = []
    name_regex = re.compile(name_regex)
    for name_token in name_tokens:
        name = name_token.value
        if name_regex.fullmatch(name) is None:
            problems.append(Problem(
                name=problem_name,
                description=description_template.format(name),
                line=name_token.line,
                column=name_token.column,
            ))
    return problems


def _gather_rule_name_tokens(parse_tree, rules):
    name_tokens_per_rule = {rule:[] for rule in rules}
    for node in parse_tree.iter_subtrees():
        if isinstance(node, Tree) and node.data in rules:
            rule_name = node.data
            name_token = _find_name_token(node)
            assert name_token is not None
            name_tokens_per_rule[rule_name].append(name_token)
    return name_tokens_per_rule


def _find_name_token(tree):
    for child in tree.children:
        if isinstance(child, Token) and child.type == 'NAME':
            return child
    return None