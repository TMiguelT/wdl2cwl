import os
import re
import json
import logging
import sys

__version__ = '0.2'

# set up logging
logger = logging.getLogger('Main')
logger.setLevel(logging.INFO)
ch = logging.StreamHandler()
ch.setLevel(logging.INFO)
logger.addHandler(ch)


def copy_step_outputs_to_workflow_outputs(step, outputs, **kwargs):
    def _find_type():
        task = kwargs['tasks'].get(step['id'], "")
        if task:
            for output_param in task['outputs']:
                if output_param['id'] == id:
                    if 'scatter' in step:
                        return {'type': 'array',
                                'items': output_param['type']}
                    else:
                        return output_param['type']
        else:
            return "Any"

        for output in step['out']:
            if type(output) is dict:
                id = output['id']
            else:
                id = output
            outputs.append({
                "id": step['id'] + '_' + id,
                "type": _find_type(),
                "outputSource": '#' + step['id'] + '/' + id
            })


def strip_special_ch(string):
    return string.strip('"\'')


def get_handlers(module_name):
    handlers = {}

    m = sys.modules[module_name]
    for k, v in m.__dict__.copy().items():
        if k.startswith("handle"):
            handlers[k[6:]] = v
    return handlers


def find_asts(ast_root, name):
    nodes = []
    if class_name(ast_root) == 'AstList':
        for node in ast_root:
            nodes.extend(find_asts(node, name))
    elif class_name(ast_root) == 'Ast':
        if ast_root.name == name:
            nodes.append(ast_root)
        for attr_name, attr in ast_root.attributes.items():
            nodes.extend(find_asts(attr, name))
    return nodes


def pick_symbol(item, *symbols):
    """
    Picks the first matching attribute from the provided item. Used mostly for multi-version compatibility
    """
    for symbol in symbols:
        if symbol in item.attributes:
            return item.attr(symbol)
    raise Exception('None of the provided symbols were available attributes')


def class_name(obj):
    """
    Return the object's class name as a string
    """
    return obj.__class__.__name__


def export_tool(tool, directory, quiet=False):
    if not quiet:
        print(json.dumps(tool, indent=4))
    data = main_template.render(version=__version__,
                                code=json.dumps(tool, indent=4))
    filename = '{0}.cwl'.format(tool['id'])
    filename = os.path.join(directory, filename)
    with open(filename, 'w') as f:
        f.write(data)
    logger.info('Generated file {0}'.format(filename))


def export_expression_tool(tool, substitutions, directory):
    replacements = dict([sub for sub in substitutions.values()])
    pattern = re.compile('|'.join(replacements.keys()))
    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           'expression-tools', tool)) as source:
        with open(os.path.join(directory, tool), 'w') as target:
            for line in source:
                target.write(pattern.sub(lambda x: replacements[x.group()], line))
