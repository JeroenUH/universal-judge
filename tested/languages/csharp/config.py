import logging
import re
from pathlib import Path
from typing import TYPE_CHECKING, Dict, List, Mapping, Optional, Set, Tuple

from tested.datatypes import AllTypes
from tested.dodona import AnnotateCode, Message, Status
from tested.features import Construct, TypeSupport
from tested.internationalization import get_i18n_string
from tested.languages.config import CallbackResult, Command, Language
from tested.languages.conventionalize import (
    EXECUTION_PREFIX,
    Conventionable,
    NamingConventions,
    conventionalize_namespace,
    submission_file,
    submission_name,
)
from tested.serialisation import FunctionCall, Statement, Value

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from tested.languages.generation import PreparedExecutionUnit

# Where the results of the compilation are stored.
OUTPUT_DIRECTORY = "all-outputs"


class CSharp(Language):
    def initial_dependencies(self) -> List[str]:
        return ["dotnet.csproj", "Values.cs", "EvaluationResult.cs"]

    def needs_selector(self):
        return True

    def file_extension(self) -> str:
        return "cs"

    def naming_conventions(self) -> Dict[Conventionable, NamingConventions]:
        return {
            "namespace": "pascal_case",
            "function": "pascal_case",
            "identifier": "pascal_case",
            "property": "pascal_case",
            "class": "pascal_case",
            "global_identifier": "macro_case",
        }

    def supported_constructs(self) -> Set[Construct]:
        return {
            Construct.OBJECTS,
            Construct.EXCEPTIONS,
            Construct.FUNCTION_CALLS,
            Construct.ASSIGNMENTS,
            Construct.HETEROGENEOUS_COLLECTIONS,
            Construct.HETEROGENEOUS_ARGUMENTS,
            Construct.EVALUATION,
            Construct.NAMED_ARGUMENTS,
            Construct.DEFAULT_PARAMETERS,
            Construct.GLOBAL_VARIABLES,
        }

    def datatype_support(self) -> Mapping[AllTypes, TypeSupport]:
        return {
            "integer": "supported",
            "real": "supported",
            "char": "reduced",
            "text": "supported",
            "boolean": "supported",
            "sequence": "supported",
            "set": "supported",
            "map": "supported",
            "nothing": "supported",
            "undefined": "reduced",
            "null": "reduced",
            "int8": "supported",
            "uint8": "supported",
            "int16": "supported",
            "uint16": "supported",
            "int32": "supported",
            "uint32": "supported",
            "int64": "supported",
            "uint64": "supported",
            "bigint": "supported",
            "single_precision": "supported",
            "double_precision": "supported",
            "array": "supported",
            "list": "supported",
            "tuple": "supported",
        }

    def compilation(self, files: List[str]) -> CallbackResult:
        # In C#, all output files are located in a subdirectory, so we just
        # want to copy over the subdirectory.
        def file_filter(file: Path) -> bool:
            return file.parent.name == OUTPUT_DIRECTORY

        executable_file = files[-1]
        name = Path(executable_file).stem
        args = [
            "dotnet",
            "build",
            "--no-incremental",
            "--output",
            OUTPUT_DIRECTORY,
            "--force",
            "--nologo",
            f"-p:AssemblyName={name}",
            f"-p:StartupObject=Tested.{name}",
            "-consoleloggerparameters:NoSummary",
        ]

        return args, file_filter

    def execution(self, cwd: Path, file: str, arguments: List[str]) -> Command:
        file = OUTPUT_DIRECTORY + "/" + file
        return ["dotnet", file, *arguments]

    def find_main_file(
        self, files: List[Path], name: str, precompilation_messages: List[str]
    ) -> Tuple[Optional[Path], List[Message], Status, List[AnnotateCode]]:
        # TODO: specify the extension (if any) of the output files, so we don't need to
        # override this.
        logger.debug("Finding %s in %s", name, files)
        messages = []
        possible_main_files = [
            x for x in files if x.name.startswith(name) and x.suffix == ".dll"
        ]
        if possible_main_files:
            return possible_main_files[0], messages, Status.CORRECT, []
        else:
            messages.extend(precompilation_messages)
            messages.append(get_i18n_string("languages.config.unknown.compilation"))
            return None, messages, Status.COMPILATION_ERROR, []

    def modify_solution(self, solution: Path):
        # noinspection PyTypeChecker
        with open(solution, "r") as file:
            contents = file.read()

        if "class" in contents:
            return  # No top-level statements; we are happy...

        class_name = submission_name(self)
        result = f"""\
using System;
using System.IO;
using System.Collections.Generic;
using System.Linq;
using System.Net.Http;
using System.Threading;
using System.Threading.Tasks;

class {class_name}
{{
    public static void Main(string[] args)
    {{
        {contents}
    }}
}}
        """

        # noinspection PyTypeChecker
        with open(solution, "w") as file:
            file.write(result)

    def cleanup_stacktrace(self, stacktrace: str) -> str:
        execution = conventionalize_namespace(self, EXECUTION_PREFIX)
        execution_submission_location_regex = (
            rf"{self.config.dodona.workdir}/common/{execution}[0-9]+.cs"
        )
        submission_location = (
            self.config.dodona.workdir / "common" / submission_file(self)
        )
        submission_location_regex = rf"{submission_location.resolve()}:line ([0-9]+)"
        compilation_location_regex = rf"{submission_location.resolve()}\((\d+),(\d+)\)"
        compilation_suffix = f" [{self.config.dodona.workdir}/common/dotnet.csproj]"

        resulting_lines = ""
        for line in stacktrace.splitlines(keepends=True):
            # If we encounter an execution location, we are done.
            if re.search(execution_submission_location_regex, line):
                break

            if "Determining projects to restore..." in line:
                continue
            if f"Restored {self.config.dodona.workdir}" in line:
                continue

            line = re.sub(submission_location_regex, r"<code>:\1", line)
            line = re.sub(compilation_location_regex, r"<code>:\1:\2", line)
            line = line.replace(compilation_suffix, "")
            resulting_lines += line

        return resulting_lines

    def compiler_output(
        self, stdout: str, stderr: str
    ) -> Tuple[List[Message], List[AnnotateCode], str, str]:
        submission = submission_name(self)
        message_regex = (
            rf"{submission}\((\d+),(\d+)\): (error|warning) ([A-Z0-9]+): (.*) \["
        )
        messages = re.findall(message_regex, stdout)
        annotations = []
        for message in messages:
            annotations.append(
                AnnotateCode(
                    row=int(message[0]),
                    text=message[4],
                    externalUrl="https://learn.microsoft.com/dotnet/csharp/language-reference/compiler-messages/",
                    column=int(message[1]),
                    type=message[2],
                )
            )

        return [], annotations, stdout, stderr

    def generate_statement(self, statement: Statement) -> str:
        from tested.languages.csharp import generators

        return generators.convert_statement(statement, full=True)

    def generate_execution_unit(self, execution_unit: "PreparedExecutionUnit") -> str:
        from tested.languages.csharp import generators

        return generators.convert_execution_unit(execution_unit)

    def generate_selector(self, contexts: List[str]) -> str:
        from tested.languages.csharp import generators

        return generators.convert_selector(contexts)

    def generate_check_function(self, name: str, function: FunctionCall) -> str:
        from tested.languages.csharp import generators

        return generators.convert_check_function(function)

    def generate_encoder(self, values: List[Value]) -> str:
        from tested.languages.csharp import generators

        return generators.convert_encoder(values)
