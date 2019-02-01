import inflection

class WdlConverter:
    def __init__(self):
        self.expression_tools = []

    def handle(self, name, item, **kwargs):
        underscore = inflection.underscore(name)
        handler = getattr(self, 'handle_' + underscore)
        handler(item, **kwargs)

    def ihandle(self, i, **kwargs):
        raise NotImplementedError()
