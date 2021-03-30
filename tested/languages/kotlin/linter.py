import json
import logging
from pathlib import Path
from typing import List, Tuple

from tested.configs import Bundle
from tested.dodona import Message, AnnotateCode, ExtendedMessage, Permission, \
    Severity
from tested.internationalization import get_i18n_string
from tested.judge.utils import run_command

logger = logging.getLogger(__name__)


def run_ktlint(bundle: Bundle, submission: Path, remaining: float) \
        -> Tuple[List[Message], List[AnnotateCode]]:
    """
    Calls ktlint to annotate submitted source code and adds resulting score and
    annotations to tab.
    """
    config = bundle.config
    language_options = bundle.config.config_for()

    command = ["ktlint", "--reporter=json"]

    if language_options.get("editorconfig", None):
        command.append("--editorconfig="
                       f"{config.resources / language_options.get('editorconfig')}")

    if language_options.get("disabled_rules_ktlint", None):
        rules = language_options["disabled_rules_ktlint"]
        if isinstance(rules, list):
            rules = ",".join(rules)
        if "filename" not in rules:
            rules += ",filename"
        command.append(f"--disabled_rules={rules}")
    else:
        command.append("--disabled_rules=filename")

    if language_options.get("ktlint_ruleset", None):
        command.append(
            f"--ruleset={config.resources / language_options.get('ktlint_ruleset')}"
        )

    if language_options.get("ktlint_experimental", True):
        command.append("--experimental")

    command.append(submission.absolute())

    execution_results = run_command(
        directory=submission.parent,
        timeout=remaining,
        command=command
    )

    if execution_results is None:
        return [], []

    if execution_results.timeout or execution_results.memory:
        return [get_i18n_string(
            "languages.kotlin.linter.timeout") if execution_results.timeout else
                get_i18n_string("languages.kotlin.linter.memory")], []

    try:
        ktlint_objects = json.loads(execution_results.stdout)
    except Exception as e:
        logger.warning("KTLint produced bad output", exc_info=e)
        return [get_i18n_string("languages.kotlin.linter.output"),
                ExtendedMessage(
                    description=str(e),
                    format='code',
                    permission=Permission.STAFF
                )], []
    annotations = []

    for ktlint_object in ktlint_objects:
        if Path(ktlint_object['file']).name != submission.name:
            continue
        annotations.extend(map(lambda x: AnnotateCode(
            row=max(int(x['line']) - 1, 0),
            text=x['message'],
            column=max(int(x['column']) - 1, 0),
            type=Severity.ERROR,
        ), ktlint_object['errors']))

    # sort linting messages on line, column and code
    annotations.sort(key=lambda a: (a.row, a.column, a.text))
    return [], annotations
