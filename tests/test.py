import pytest
from pathlib2 import Path
from wdl2cwl.main import process_file
import wdl_parser
from wdl2cwl.converters import wdl_converter, draft_2, version_1
import tempfile
import cwltool.factory

fac = cwltool.factory.Factory()

test_cases = [ path for path in (Path(__file__).parent / 'test-data').iterdir() if path.is_dir()]


@pytest.mark.parametrize("dir", test_cases, ids=[path.stem for path in test_cases])
def test_directory(dir):
    with tempfile.TemporaryDirectory() as tempd:
        process_file(
            dir / 'task.wdl',
            parser=wdl_parser.parsers['draft-2'],
            converter=draft_2.Draft2Converter(),
            out_dir=Path(tempd)
        )

        for file in Path(tempd).iterdir():
            # Test that the CWL validates
            fac.make(str(file))