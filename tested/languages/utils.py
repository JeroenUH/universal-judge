import html
import logging
import math
import os
import re
import warnings
from pathlib import Path
from typing import TYPE_CHECKING, List, Optional, Tuple

from tested.configs import GlobalConfig
from tested.dodona import AnnotateCode, ExtendedMessage, Message, Permission
from tested.languages.conventionalize import submission_name

if TYPE_CHECKING:
    from tested.languages.config import Language

_logger = logging.getLogger(__name__)
code_regex = re.compile(r"<code>:(\d+)")


def cleanup_description(lang_config: "Language", description: str) -> str:
    return description.replace(rf"{submission_name(lang_config)}.", r"", 1)


def jvm_memory_limit(config: GlobalConfig) -> int:
    """
    Get the memory limit in bytes. Java Virtual Machine (JVM) requires this to be a
    multiple of 1024.
    See https://docs.oracle.com/en/java/javase/14/docs/specs/man/java.html
    """
    limit = int(config.dodona.memory_limit)
    limit = (limit // 1024) * 1024
    return limit


# Idea and original code: dodona/judge-pythia
def jvm_cleanup_stacktrace(stacktrace: str, submission_filename: str) -> str:
    context_file_regex = re.compile(r"(Context[0-9]+|Selector)")
    unresolved_main_regex = r"error: unresolved reference: solutionMain"
    unresolved_reference_regex = re.compile(
        r"(error: unresolved reference: [a-zA-Z$_0-9]+)"
    )
    stacktrace = stacktrace.splitlines(True)

    skip_line, lines = False, []
    for line in stacktrace:
        line = line.strip("\n")

        if not line:
            continue

        # skip line if not a new File line is started
        if context_file_regex.search(line):
            if unresolved_main_regex in line:
                lines.append("error: unresolved reference: main\n")
            else:
                match = unresolved_reference_regex.search(line)
                if match:
                    lines.append(match[0] + "\n")
            skip_line = True
            continue
        elif skip_line and (line.startswith(" ") and "at" not in line):
            continue

        # replace references to local names
        if submission_filename in line:
            line = line.replace(submission_filename, "<code>")
            line = line.replace("Kt.solutionMain", "Kt.main")
        elif "at " in line:
            skip_line = True
            continue
        skip_line = False
        lines.append(line + "\n")

    return "".join(lines)


def jvm_stderr(
    self: "Language", stderr: str
) -> Tuple[List[Message], List[AnnotateCode], str]:
    warnings.warn("Deprecated...", category=DeprecationWarning)
    # Identifier to separate testcase output
    identifier = f"--{self.config.testcase_separator_secret}-- SEP"
    context_identifier = f"--{self.config.context_separator_secret}-- SEP"

    return (
        [],
        [],
        context_identifier.join(
            identifier.join(
                self.cleanup_stacktrace(testcase)
                for testcase in context.split(identifier)
            )
            for context in stderr.split(context_identifier)
        ),
    )


def haskell_solution(lang_config: "Language", solution: Path):
    """Support implicit modules if needed."""
    if lang_config.config.dodona.config_for().get("implicitModule", True):
        name = submission_name(lang_config)
        # noinspection PyTypeChecker
        with open(solution, "r") as file:
            contents = file.read()
        # noinspection PyTypeChecker
        with open(solution, "w") as file:
            original_lines = contents.split("\n")
            i = next(
                i for i, line in enumerate(original_lines) if not line.startswith("{-#")
            )
            result = f"module {name} where\n"
            resulting_lines = original_lines[:i] + [result] + original_lines[i:]
            file.write("\n".join(resulting_lines))


def executable_name(basename: str) -> str:
    """
    Utility function that will

    :param basename: The name of the executable without extension.

    :return: The executable with extension corresponding to the platform.
    """
    if os.name == "nt":
        return f"{basename}.exe"
    else:
        return basename


def limit_output(
    output: str,
    limit_characters: int = 512,
    max_lines: int = 20,
    ellipsis_str: str = "...",
) -> str:
    """
    Utility function for limiting a string output

    :param output: String that possible needs to be abbreviated
    :param limit_characters: Maximum characters used in the output
    :param max_lines: Maximum lines in the output
    :param ellipsis_str: ellipsis used when abbreviated is needed

    :return: The abbreviated 'output' if needed otherwise the 'output' itself
    """
    lines = output.splitlines()
    # Case character limit not exceeded and line limit not exceeded
    if len(output) <= limit_characters and len(lines) <= max_lines:
        return output
    # Case character limit exceeded
    max_chars = limit_characters - len(ellipsis_str)
    forward_buffer = []
    backward_buffer = []
    len_lines = len(lines)
    for f in range(math.ceil(min(max_lines - 1, len_lines) / 2)):
        r = len_lines - f - 1
        # Case last lines to consider are the same
        if f == r:
            forward_buffer.append(lines[f][: (max_chars - 1)])
        # Otherwise
        else:
            next_line, prev_line = lines[f], lines[r]
            current_length = len(next_line) + len(prev_line) + 2
            # Both lines can be add in full
            if current_length < max_chars:
                forward_buffer.append(next_line)
                backward_buffer.append(prev_line)
                max_chars -= current_length
            # Lines must be limited
            else:
                half = max_chars / 2
                # Next line can be add in full
                if len(next_line) + 2 < max_chars:
                    forward_buffer.append(next_line)
                    max_chars -= len(next_line) + 2
                    backward_buffer.append(prev_line[-max_chars:])
                # Prev line can be add in full
                elif len(prev_line) + 2 < max_chars:
                    backward_buffer.append(prev_line)
                    max_chars -= len(prev_line) + 2
                    forward_buffer.append(next_line[:max_chars])
                # Both lines needed abbreviation
                else:
                    forward_buffer.append(next_line[: math.ceil(half - 1)])
                    backward_buffer.append(prev_line[-math.floor(half - 1) :])
                # Terminate loop because character limit reached
                break
    # Concat buffer
    return "\n".join(forward_buffer + [ellipsis_str] + backward_buffer[::-1])


def _convert_stacktrace_to_html(stacktrace: str) -> ExtendedMessage:
    link_replacement = r'<a href="#" class="tab-link" data-tab="code" data-line="\1">&lt;code&gt;:\1</a>'
    # Escape special characters.
    stacktrace = html.escape(stacktrace)
    # Add links to code.
    stacktrace = re.sub(code_regex, link_replacement, stacktrace)
    # We cannot generate a "pre" element, since that is ugly.
    generated = f"<div class='code'>Traceback:{stacktrace.strip()}</div>"
    # Ensure newlines.
    generated = generated.replace("\n", "<br>")
    return ExtendedMessage(
        description=generated,
        format="html",
        permission=Permission.STUDENT,
    )


def _replace_code_line_number(offset: int, stacktrace: str) -> str:
    def modify_line_number(match: re.Match) -> str:
        current_number = int(match.group(1))
        return "<code>:" + str(current_number + offset)

    return re.sub(code_regex, modify_line_number, stacktrace)


def convert_stacktrace_to_clickable_feedback(
    lang: "Language", stacktrace: Optional[str]
) -> Optional[ExtendedMessage]:
    """
    Convert a stacktrace to an HTML message with clickable links to the submission.

    In this process, the stacktrace is first passed to the language config to clean
    up the stacktrace. Then the code links are updated for shifted line numbers, and
    finally, the code links are converted to actual links.

    :param lang: The language config.
    :param stacktrace: The stacktrace to clean up.
    :return: A clickable feedback message.
    """
    if not stacktrace:
        return None
    cleaned_stacktrace = lang.cleanup_stacktrace(stacktrace)
    updated_stacktrace = _replace_code_line_number(
        lang.config.dodona.source_offset, cleaned_stacktrace
    )
    html_stacktrace = _convert_stacktrace_to_html(updated_stacktrace)
    return html_stacktrace
