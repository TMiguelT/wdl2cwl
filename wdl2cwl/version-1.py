def handleTask(item, **kwargs):
    tool = {"id": ihandle(item.attr("name"), **kwargs),
            "class": "CommandLineTool",
            "cwlVersion": "v1.0",
            "baseCommand": [],
            "requirements": [{"class": "ShellCommandRequirement"},
                             {"class": "InlineJavascriptRequirement"}],
            "inputs": [],
            "outputs": []}

    filevars = kwargs.get("filevars", set())
    for i in item.attr("sections"):
        # NO! declarations can be expressions of other inputs and thus must not be treated as file inputs
        tool["inputs"].append(ihandle(i, context=tool,
                                      assignments=kwargs.get("assignments", {}),
                                      filevars=filevars,
                                      **kwargs))
    for i in item.attr("sections"):
        ihandle(i, context=tool, assignments=kwargs.get("assignments", {}),
                filevars=filevars, **kwargs)

    return tool
