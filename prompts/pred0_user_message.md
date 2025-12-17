[[ ## question ## ]]
{question}

[[ ## trajectory ## ]]
{trajectory}


Respond with the corresponding output fields, starting with the field `[[ ## next_thought ## ]]`, then `[[ ## next_tool_name ## ]]` (must be formatted as a valid Python Literal[search_courseware, lookup_courseware, finish]), then `[[ ## next_tool_args ## ]]` (must be formatted as a valid Python dict[str, Any]), and then ending with the marker for `[[ ## completed ## ]]`.