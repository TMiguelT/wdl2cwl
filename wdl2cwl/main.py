from __future__ import print_function

import argparse
import os
import wdl_parser
from wdl2cwl import util
from jinja2 import Environment, FileSystemLoader

env = Environment(
    loader=FileSystemLoader(os.path.abspath(os.path.join(os.path.dirname(__file__), 'templates'))),
    trim_blocks=True,
    lstrip_blocks=True)
main_template = env.get_template('cwltool.j2')
expression_tools = []  # [(file, SUBSTITUTIONS)] // SUBSTITUTIONS = {'path/to/substitute', (term, sub)}


def printstuff(wdl_code, parser, ihandle, directory=os.getcwd(), quiet=False):
    # Parse source code into abstract syntax tree
    ast = parser.parse(wdl_code).ast()
    # print(ast.dumps(indent=2))

    tasks = {}

    # Find all 'Task' ASTs
    task_asts = util.find_asts(ast, 'Task')
    for task_ast in task_asts:
        tool = ihandle(task_ast)
        # cwl.append(a)
        util.export_tool(tool, directory, quiet=quiet)
        tasks[ihandle(task_ast.attr("name"))] = tool

    # Find all 'Workflow' ASTs
    workflow_asts = util.find_asts(ast, 'Workflow')
    for workflow_ast in workflow_asts:
        wf = ihandle(workflow_ast, tasks=tasks)
        util.export_tool(wf, directory, quiet)

    for expression_tool in expression_tools:
        util.export_expression_tool(expression_tool[0], expression_tool[1], directory)

    main_template.render()


def process_file(file, args):
    with open(file) as f:
        k = f.read()
    k.replace('\n', '')
    if args.directory:
        args.directory = os.path.abspath(args.directory)
        if os.path.isdir(args.directory):
            os.chdir(args.directory)
        else:
            os.mkdir(args.directory)
            os.chdir(args.directory)
    else:
        args.directory = os.getcwd()
    if not args.no_folder:
        cwl_directory = os.path.join(args.directory, os.path.basename(os.path.abspath(file)).replace('.wdl', ''))
        os.mkdir(cwl_directory)
        printstuff(k, args.parser, cwl_directory, args.quiet)
    else:
        printstuff(k, args.parser, directory=args.directory, quiet=args.quiet)


def main():
    parser = argparse.ArgumentParser(description='Convert a WDL workflow to CWL')
    parser.add_argument('workflow', help='a WDL workflow or a directory with WDL files')
    parser.add_argument('--parser', choices=wdl_parser.parsers.values(), type=lambda key: wdl_parser.parsers[key],
                        help='WDL version to use for parsing')
    parser.add_argument('-d', '--directory', help='Directory to store CWL files')
    parser.add_argument('-q', '--quiet', action='store_true', help='Do not print generated files to stdout')
    parser.add_argument('--no-folder', action='store_true', help='Do not create a separate folder for each toolset')
    args = parser.parse_args()
    args.workflow = os.path.abspath(args.workflow)
    if os.path.isdir(args.workflow):
        for el in os.listdir(args.workflow):
            if el.endswith('.wdl'):
                try:
                    process_file(os.path.join(args.workflow, el), args)
                except Exception as e:
                    util.logger.error("Error while processing file {0}: {1}".format(el, e))
                    pass
    else:
        process_file(args.workflow, args)


if __name__ == '__main__':
    main()
