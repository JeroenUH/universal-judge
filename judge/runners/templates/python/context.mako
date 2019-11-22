## Code to execute one test context.
import sys
import values
import evaluator_${context_id}

## Set the main arguments.
sys.argv.extend([\
% for argument in main_arguments:
    <%include file="value.mako" args="value=argument"/>\
% endfor
])

## Open the output files.
evaluator_${context_id}.open_outputs()

## Import the code for the first time.
import ${submission_name}

## Handle test cases.
% for additional in additionals:
    sys.stderr.write("--${secret_id}-- SEP")
    sys.stdout.write("--${secret_id}-- SEP")
    evaluator_${context_id}.value_write("--${secret_id}-- SEP")
    evaluator_${context_id}.evaluate_${context_id}_${loop.index}(${submission_name}.<%include file="function.mako" args="function=additional.function" />)
% endfor

## Close output files.
evaluator_${context_id}.close_outputs()
