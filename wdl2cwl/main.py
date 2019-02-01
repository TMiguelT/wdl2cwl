import argparse
import os
from pathlib import Path
import wdl_parser
from wdl2cwl import util
from wdl2cwl.converters import wdl_converter, draft_2, version_1
from jinja2 import Environment, FileSystemLoader

env = Environment(
    loader=FileSystemLoader(os.path.abspath(os.path.join(os.path.dirname(__file__), 'templates'))),
    trim_blocks=True,
    lstrip_blocks=True)
main_template = env.get_template('cwltool.j2')


def convert_file(
        wdl_code: str,
        parser,
        converter: wdl_converter.WdlConverter,
        out_dir: Path = Path(),
        quiet: bool = False
):
    # Parse source code into abstract syntax tree
    ast = parser.parse(wdl_code).ast()
    # print(ast.dumps(indent=2))

    tasks = {}

    # Find all 'Task' ASTs
    task_asts = util.find_asts(ast, 'Task')
    for task_ast in task_asts:
        tool = converter.ihandle(task_ast)
        # cwl.append(a)
        util.export_tool(tool, out_dir, quiet=quiet)
        tasks[converter.ihandle(task_ast.attr("name"))] = tool

    # Find all 'Workflow' ASTs
    workflow_asts = util.find_asts(ast, 'Workflow')
    for workflow_ast in workflow_asts:
        wf = converter.ihandle(workflow_ast, tasks=tasks)
        util.export_tool(wf, out_dir, quiet)

    for expression_tool in converter.expression_tools:
        util.export_expression_tool(expression_tool[0], expression_tool[1], out_dir)

    main_template.render()


def process_file(
        wdl: Path,
        parser,
        converter: wdl_converter.WdlConverter,
        out_dir: Path,
        quiet: bool = False,
        sep_dir: bool = False
):
    """
    Converts a WDL file to CWL
    """
    # Read the WDL
    text = wdl.read_text().replace('\n', '')

    # Create the output directory if it doesn't exist
    if out_dir:
        if not out_dir.exists():
            out_dir.mkdir()

    if sep_dir:
        cwl_directory = out_dir / wdl.absolute().name.replace('.wdl', '')
        cwl_directory.mkdir()
        convert_file(text, parser, converter, out_dir=cwl_directory, quiet=quiet)
    else:
        convert_file(text, parser, converter, out_dir=out_dir, quiet=quiet)


def process_path(location: Path, *args, **kwargs):
    """
    Converts a Path, pointing either to a WDL file or a directory of WDL files
    """
    if location.is_dir():
        for el in location.iterdir():
            if el.suffix == '.wdl':
                try:
                    process_file(el, *args, **kwargs)
                except Exception as e:
                    util.logger.error("Error while processing file {0}: {1}".format(el, e))
                    pass
    else:
        process_file(location, *args, **kwargs)


converters = {
    'draft-2': draft_2.Draft2Converter,
    '1.0': version_1.Version1Converter,
    'draft-3': version_1.Version1Converter
}


def get_parser() -> argparse.ArgumentParser:
    """
    Returns the parser, so that other tools like Sphinx can use the parser separately
    """
    parser = argparse.ArgumentParser(description='Convert a WDL workflow to CWL')
    parser.add_argument('workflow', type=Path, help='a WDL workflow or a directory with WDL files')
    parser.add_argument('--parser', choices=wdl_parser.parsers.keys(), help='WDL version to use for parsing')
    parser.add_argument('-d', '--directory', type=Path, help='Directory to store CWL files')
    parser.add_argument('-q', '--quiet', action='store_true', help='Do not print generated files to stdout')
    parser.add_argument('--no-folder', action='store_false', dest='sep_dir',
                        help='Do not create a separate folder for each toolset')
    return parser


def main():
    """
    CLI entrypoint
    """
    args = get_parser().parse_args()
    process_path(
        args.workflow,
        parser=wdl_parser.parsers[args.parser],
        converter=converters[args.parser],
        out_dir=args.directory,
        quiet=args.quiet,
        sep_dir=args.sep_dir
    )


if __name__ == '__main__':
    main()
