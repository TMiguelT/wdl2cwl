import re
from wdl2cwl import util
from wdl2cwl.converters.wdl_converter import WdlConverter


class Draft2Converter(WdlConverter):
    typemap = {
        "Int": "int",
        "File": "File",
        "String": "string",
        "Array": "array",
        "Float": "float",
        "Boolean": "boolean"
    }

    def ihandle(self, i, **kwargs):
        """
        Process a symbol. Terminals are converted into an appropriate Python representation, and nonterminals are processed
        by the corresponding handleXXX function
        """
        if util.class_name(i) == 'Terminal':
            if i.str == "string":
                return '"%s"' % i.source_string
            elif i.str == "integer":
                return i.source_string
            elif i.str == "cmd_part":
                return i.source_string
            elif i.str == "type":
                return self.typemap[i.source_string]
            elif i.str == "fqn":
                return "#" + i.source_string
            elif i.str == "asterisk":
                return i.source_string
            elif i.str in "identifier":
                if kwargs.get("in_expression"):
                    # kw.get("depends_on").add(i)
                    if i.source_string in kwargs.get("filevars", ""):
                        return "inputs.%s.path" % i.source_string
                    else:
                        return "inputs." + i.source_string
                else:
                    return i.source_string
            else:
                raise NotImplementedError("Unknown terminal '%s'" % i.str)
        else:
            return self.handle(i.name, i, **kwargs)

    def handle_document(self, item, **kwargs):
        defs = []
        for i in item.attr("imports"):
            self.ihandle(i, **kwargs)
        for i in item.attr("definitions"):
            defs.append(self.ihandle(i, **kwargs))
        return defs

    def handle_import(self, item, **kwargs):
        raise NotImplementedError('Import not implemented')

    def handle_task(self, item, **kwargs):
        tool = {
            "id": self.ihandle(item.attr("name"), **kwargs),
            "class": "CommandLineTool",
            "cwlVersion": "v1.0",
            "baseCommand": [],
            "requirements": [
                {"class": "ShellCommandRequirement"},
                {"class": "InlineJavascriptRequirement"}
            ],
            "inputs": [],
            "outputs": []
        }

        filevars = kwargs.get("filevars", set())
        for i in item.attr("declarations"):
            # NO! declarations can be expressions of other inputs and thus must not be treated as file inputs
            tool["inputs"].append(self.ihandle(
                i,
                context=tool,
                assignments=kwargs.get("assignments", {}),
                filevars=filevars,
                **kwargs
            ))
        for i in item.attr("sections"):
            self.ihandle(
                i,
                context=tool,
                assignments=kwargs.get("assignments", {}),
                filevars=filevars, **kwargs
            )

        return tool

    def handle_workflow(self, item, **kwargs):
        wf = {
            "id": self.ihandle(item.attr("name")),
            "class": "Workflow",
            "cwlVersion": "v1.0",
            "inputs": [],
            "outputs": [],
            "requirements": [
                {"class": "InlineJavascriptRequirement"}
            ],
            "steps": []
        }
        assignments = {}
        filevars = set()
        for i in item.attr("body"):
            if i.name == "Call":
                wf["steps"].append(self.ihandle(
                    i,
                    context=wf,
                    assignments=assignments,
                    filevars=filevars,
                    **kwargs
                ))
            elif i.name == "Declaration":
                # NO! declarations can be expressions of other inputs and thus must not be treated as inputs
                inp = self.ihandle(
                    i,
                    context=wf,
                    assignments=assignments,
                    filevars=filevars,
                    **kwargs
                )
                if inp:
                    wf["inputs"].append(inp)
            elif i.name == "WorkflowOutputs":
                wf["outputs"] = self.ihandle(i, context=wf, **kwargs)
            elif i.name == "Scatter":
                wf["steps"].extend(self.ihandle(
                    i,
                    context=wf,
                    assignments=assignments,
                    filevars=filevars,
                    **kwargs
                ))
            else:
                raise NotImplementedError

        if wf['outputs'] == []:
            for step in wf['steps']:
                util.copy_step_outputs_to_workflow_outputs(step, wf['outputs'], **kwargs)
        return wf

    def handle_runtime(self, item, **kwargs):
        for runtimeRequirement in item.attr('map'):
            key = self.ihandle(runtimeRequirement.attr('key'))
            if key == 'docker':
                value = self.ihandle(runtimeRequirement.attr('value'))
                if type(value) is list:
                    value = value[0]  # if there are several Docker images, pick the first one (due to CWL restrictions)
                kwargs['context']['requirements'].append({
                    'class': 'DockerRequirement',
                    'dockerPull': util.strip_special_ch(value)
                })
            elif key == 'memory':
                kwargs['context']['requirements'].append({
                    'class': 'ResourceRequirement',
                    'ramMin': util.strip_special_ch(self.ihandle(runtimeRequirement.attr('value')))
                })
            else:
                util.logger.warning('Field "{0}" is ignored'.format(key))

    def handle_type(self, item, **kwargs):
        def _convert_bracket_notation(_type):
            if _type.endswith(']'):
                return {'type': 'array',
                        'items': _type.split('[')[0]}
            else:
                return _type

        param_type = self.ihandle(item.attr('name'))
        subtype = self.ihandle(item.attr('subtype')[0])
        if param_type == 'array' and not subtype.endswith(']'):
            return subtype + '[]'
        else:
            return {'type': param_type,
                    'items': _convert_bracket_notation(subtype)}

    def handle_declaration(self, item, context=None, assignments=None, filevars=None, **kwargs):
        param_id = self.ihandle(item.attr("name"))
        param_type = self.ihandle(item.attr("type"), **kwargs)
        expression = item.attr("expression")
        kwargs['context'] = context
        if expression is None:
            # assignments[param_id] = "#%s/%s" % (context["id"], param_id)
            if param_type == "File":
                filevars.add(param_id)
            return {
                "id": param_id,
                "type": param_type
            }
        else:
            kwargs['outputName'] = param_id
            result = self.ihandle(expression, **kwargs)
            if result:
                # if result[0] in {'\'', '"'}  # expression is string
                if result.startswith('['):
                    result = eval(result)
                else:
                    result = '$(' + result + ')'
                return {
                    "id": param_id,
                    "type": param_type,
                    "default": result
                }

    def handle_raw_command(self, item, context=None, **kwargs):
        s = body = ''
        symbols = []
        parts = item.attr('parts')
        if 'python' in self.ihandle(parts[0]):
            for i, part in enumerate(parts):
                # TODO: python commands
                pass
            pass
        for p in parts:
            kwargs['command'] = s
            part = self.ihandle(p, **kwargs)
            if type(part) is list:
                body += part[0]
                s += part[1]
                symbols.append(part[1])
            else:
                s += part
        if body:  # if the expr. is a function body, not a simple expr.
            symbols.append('\$\(.*?\)')
            l = re.split('(' + '|'.join(symbols) + ')', s)
            res = []
            for k in l:
                if k in set(symbols[:-1]):
                    res.append(k)
                elif '$' in k:
                    res.append(re.sub('[$()]', '', k))
                else:
                    res.append("\"" + k + "\"")
            s = ' + '.join(res)
            result = '${' + body + 'return ' + s + '}'
        else:
            result = s
        result = re.sub(r'\\\n\s*', '', result)
        result = result.strip()
        result = result.replace('\n', '')
        context["arguments"] = [{"valueFrom": result, "shellQuote": False}]

    def handle_command_parameter(self, item, context=None, **kwargs):
        attributes = item.attr('attributes')
        for option in attributes:
            key = self.ihandle(option.attr('key'))

            if key == 'sep':
                parameter = item.attr('expr').source_string
                string = parameter + '_separated'
                preprocessing = """
                var {2} = '';
                for (var i=0; i<inputs.{0}.length; i++){{
                    {2} = {2} + inputs.{0}[i].path + '{1}';
                }}
                {2} = {2}.replace(/{1}$/, '');
                """.format(parameter,
                           self.ihandle(option.attr('value')).replace('\"', ""),
                           string)

                return [preprocessing, string]

        return "$(" + self.ihandle(item.attr("expr"), in_expression=True, depends_on=set(), **kwargs) + ")"

    def handle_outputs(self, item, context=None, **kwargs):
        for a in item.attr("attributes"):
            out = {
                "id": self.ihandle(a.attr("name")),
                "type": self.ihandle(a.attr("type")),
                "outputBinding": {}
            }
            e = self.ihandle(
                a.attr("expression"),
                is_expression=True,
                depends_on=set(),
                outputs=out,
                tool=context,
                context=context,
                **kwargs
            )
            if type(e) is str:
                e = e.replace('{', '(').replace('}', ')').replace("\"", '')
                if not str(re.search('\((.+?)\)', e)).startswith('inputs'):
                    if not 'self' in e:
                        index = e.index('(')
                        e = e[:index + 1] + 'inputs.' + e[index + 1:]
            if e != "self":
                out["outputBinding"]["glob"] = e
            context["outputs"].append(out)

    def handle_function_call(self, item, **kwargs):
        function_name = self.ihandle(item.attr("name"))

        if function_name == "stdout":
            kwargs["tool"]["stdout"] = "__stdout"
            kwargs["outputs"]["outputBinding"]["glob"] = "__stdout"
            return "self[0]"

        elif function_name == "read_int":
            kwargs["outputs"]["outputBinding"]["loadContents"] = True
            return "parseInt(" + self.ihandle(item.attr("params")[0], **kwargs) + ".contents)"

        elif function_name == "read_string":
            kwargs["outputs"]["outputBinding"]["loadContents"] = True
            return self.ihandle(item.attr("params")[0], **kwargs) + ".contents"

        elif function_name == "read_tsv":
            try:
                params = [self.ihandle(param, **kwargs) for param in item.attr('params')]
                tool_name = step_name = 'read_tsv'
                tool_file = tool_name + '.cwl'
                # handling duplicate step names due to hypothetical multiple expr. tools calls
                if kwargs['context'].get('steps', ''):
                    read_tsv_steps = [step['id'] for step in kwargs['context']['steps'] if
                                      step['id'].startswith(step_name)]
                else:
                    read_tsv_steps = None
                if not read_tsv_steps:
                    step_name += '_1'
                else:
                    step_name += str(int(read_tsv_steps[-1][-1]) + 1)  # if there are step_1, step_2 - create step_3
                output_name = kwargs['outputName']
                # TODO: params[0] - looks like magic
                read_tsv_step = {
                    'id': step_name,
                    'run': tool_file,
                    'in': {
                        'infile': params[0]
                    },
                    'out': [output_name]
                }
                kwargs['context']['steps'].insert(0, read_tsv_step)
                SUBSTITUTIONS = {
                    'outputs': ('outputArray', output_name),
                    'expression': ('outputArray', output_name)
                }

                self.expression_tools.append((tool_file, SUBSTITUTIONS))
            except:
                pass

        elif function_name == 'sub':
            params = item.attr('params')
            kwargs['in_expression'] = True
            result = self.ihandle(params[0], **kwargs) + '.replace(' + self.ihandle(params[1]) + ', ' + self.ihandle(
                params[2]) + ')'
            return result
        elif function_name == 'glob':
            return [self.ihandle(param).strip('"\'') for param in item.attr('params')]
        else:
            raise NotImplementedError("Unknown function '%s'" % self.ihandle(item.attr("name")))

    def handle_call(self, item, context=None, assignments=None, **kwargs):
        if item.attr("alias") is not None:
            stepid = self.ihandle(item.attr("alias"))
        else:
            stepid = self.ihandle(item.attr("task")).strip('#')

        step = {
            "id": stepid,
            "in": [],
            "out": [],
            "run": self.ihandle(item.attr("task")).strip('#') + '.cwl'
        }

        for out in kwargs["tasks"][self.ihandle(item.attr("task")).strip('#')]["outputs"]:
            step["out"].append({"id": out["id"]})
            mem = "%s.%s" % (stepid, out["id"])
            assignments[mem] = "#%s/%s/%s" % (context["id"], stepid, out["id"])
            if out["type"] == "File":
                kwargs["filevars"].add(mem)

        b = item.attr("body")
        if b is not None:
            self.ihandle(b, context=step, assignments=assignments, **kwargs)

        for taskinp in kwargs["tasks"][self.ihandle(item.attr("task")).strip('#')]["inputs"]:
            f = [stepinp for stepinp in step["in"] if stepinp["id"] == taskinp["id"]]
            if not f and taskinp.get("default") is None:
                newinp = "%s_%s" % (stepid, taskinp["id"])
                context["inputs"].append({
                    "id": newinp,
                    "type": taskinp["type"]
                })
                step["in"].append({
                    "id": taskinp["id"],
                    "source": "%s" % (newinp)
                })

        return step

    def handle_call_body(self, item, **kwargs):
        for i in item.attr("io"):
            self.ihandle(i, **kwargs)

    def handle_scatter(self, item, **kwargs):
        scatter_requirements = [
            {'class': 'ScatterFeatureRequirement'},
            {'class': 'StepInputExpressionRequirement'}
        ]
        if scatter_requirements not in kwargs['context']['requirements']:
            kwargs['context']['requirements'].extend(scatter_requirements)
        # TODO: smart scattering (over subworkflows rather than individual steps)
        steps = []

        for task in item.attr('body'):
            if task.name == 'Declaration':
                kwargs['context']['inputs'].append(self.ihandle(task, **kwargs))
            elif task.name == 'Call':
                tool_name = self.ihandle(task.attr("task")).strip('#')
                alias = task.attr("alias")
                if alias is not None:
                    stepid = self.ihandle(alias)
                else:
                    stepid = tool_name
                step = {"id": stepid,
                        "in": [],
                        "out": [],
                        "run": tool_name + '.cwl'}
                scatter_vars = [self.ihandle(item.attr('item')), self.ihandle(item.attr('collection'))]

                # Explanation: in WDL - scatter (scatter_vars[0] in scatter_vars[1])
                kwargs['scatter_vars'] = scatter_vars
                kwargs['scatter_inputs'] = []
                kwargs['step'] = step
                for out in kwargs["tasks"][tool_name]["outputs"]:
                    step["out"].append({"id": out["id"]})

                b = task.attr("body")
                if b is not None:
                    self.ihandle(b, **kwargs)
                scatter_inputs = kwargs['scatter_inputs']
                if type(scatter_inputs) is list and len(scatter_inputs) > 1:
                    step['scatterMethod'] = 'dotproduct'
                step.update({"scatter": kwargs['scatter_inputs']})
                steps.append(step)
            else:
                raise NotImplementedError
        return steps

    def handle_io_mapping(self, item, context=None, assignments=None, filevars=None, **kwargs):
        mp = {"id": self.ihandle(item.attr("key"))}

        scatter_vars = kwargs.get('scatter_vars', '')

        value = self.ihandle(item.attr("value"))
        if value.endswith(']'):
            wdl_var = value[:-3]
        else:
            wdl_var = value
        if scatter_vars and ((wdl_var == scatter_vars[0]) or scatter_vars[0] in wdl_var):
            kwargs['scatter_inputs'].append(mp['id'])
            source = 'inputs'
            for step in context['steps']:
                if scatter_vars[1] in step['out']:
                    source = step['id']
            if source != 'inputs':
                mp["source"] = "#{0}/{1}".format(source, scatter_vars[1])
            else:
                mp['source'] = scatter_vars[1]
            if scatter_vars[1] in mp.get("source", ""):
                mp["valueFrom"] = "$(" + self.ihandle(item.attr("value"),
                                                      in_expression=False,
                                                      filevars=filevars).replace(scatter_vars[0], "self") + ")"
        else:
            value_is_literal = hasattr(item.attr("value"), 'str') and \
                               ((item.attr('value').str == 'string') or item.attr('value').str == 'integer')
            value_is_expression = hasattr(item.attr("value"), 'name')
            if value_is_literal or (value_is_expression and item.attr('value').name != 'MemberAccess'):
                mp['valueFrom'] = '$({0})'.format(value)
            elif value_is_expression and item.attr('value').name == 'MemberAccess':
                mp['source'] = '#' + value
            else:
                mp['source'] = value

        if scatter_vars:
            kwargs['step']["in"].append(mp)
        else:
            context['in'].append(mp)

    def handle_workflow_outputs(self, item, **kwargs):
        outputs = []
        for output in item.attr('outputs'):
            cwl_output = {}
            for key, value in output.attributes.items():
                if value:
                    if key == 'wildcard':
                        if self.ihandle(value) == '*':
                            # asterisk means that all outputs from the task must be copied to workflow outputs
                            for step in kwargs['context']['steps']:
                                if step['id'] == cwl_output['source_step'].strip('#'):
                                    util.copy_step_outputs_to_workflow_outputs(step, outputs, **kwargs)
                        del cwl_output['source_step']
                    elif key == 'fqn':
                        res = self.ihandle(value)
                        if type(res) is str:
                            res = res.split('.')
                            if len(res) > 1:
                                cwl_output['id'] = res[1]
                                cwl_output['outputSource'] = res[0] + '/' + res[1]
                            else:
                                cwl_output['source_step'] = res[0]
                    elif key == 'name':
                        cwl_output['id'] = self.ihandle(value)
                    elif key == 'type':
                        cwl_output['type'] = self.ihandle(value)
                    elif key == 'expression':
                        cwl_output['outputSource'] = self.ihandle(value)
            if cwl_output:
                outputs.append(cwl_output)
        return outputs

    def handle_inputs(self, item, **kwargs):
        for m in item.attr("map"):
            self.ihandle(m, **kwargs)

    def handle_optional_type(self, item, **kwargs):
        param_type = self.ihandle(item.attr('innerType'), **kwargs)
        if type(param_type) is dict:
            if param_type['type'] == 'array':
                return param_type['items'] + '[]?'
            else:
                param_type['type'] = [param_type['type'], 'null']
                return param_type
        else:
            return param_type + '?'

    def handle_parameter_meta(self, item, **kwargs):
        inputs = set(el['id'] for el in kwargs['context']['inputs'])
        for el in item.attr('map'):
            key, value = self.ihandle(el, **kwargs)
            if key in inputs:
                for i, inp in enumerate(kwargs['context']['inputs']):
                    if inp['id'] == key:
                        kwargs['context']['inputs'][i]['doc'] = value.strip('\'"')
                        break

    def handle_runtime_attribute(self, item, **kwargs):
        return self.ihandle(item.attr('key')), self.ihandle(item.attr('value'))

    def handle_array_literal(self, item, **kwargs):
        return '[' + ', '.join([self.ihandle(list_item) for list_item in item.attr('values')]).strip(' ,') + ']'

    def handle_multiply(self, ex, **kwargs):
        return self.ihandle(ex.attr("lhs"), **kwargs) + " * " + self.ihandle(ex.attr("rhs"), **kwargs)

    def handle_add(self, ex, **kwargs):
        return self.ihandle(ex.attr("lhs"), **kwargs) + " + " + self.ihandle(ex.attr("rhs"), **kwargs)

    def handle_array_or_map_lookup(self, ex, **kwargs):
        return self.ihandle(ex.attr("lhs"), **kwargs) + "[" + self.ihandle(ex.attr("rhs"), **kwargs) + ']'

    def handle_member_access(self, item, **kwargs):
        mem = self.ihandle(item.attr("lhs"), **kwargs) + "/" + self.ihandle(item.attr("rhs"), **kwargs)
        return mem
