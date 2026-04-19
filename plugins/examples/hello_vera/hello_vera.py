from core.nodes import BaseNode


class HelloWorldNode(BaseNode):
    def __init__(self):
        super().__init__(node_type="hello_world", title="Hello World")
        self.add_input_port("name", data_type="string")
        self.add_output_port("greeting", data_type="string")
        # Light inline summary via property
        self.set_property("name", "World")
        self.set_node_size(220, 120)

    def execute(self, inputs=None):
        name = None
        if isinstance(inputs, dict):
            v = inputs.get("name")
            if isinstance(v, (list, tuple)):
                name = v[0] if v else None
            else:
                name = v
        if not name:
            name = self.get_property("name", "World")
        greeting = f"Hello, {name}!"
        # Update last_result for UI and return mapping to output port
        self.set_property("greeting", greeting)
        return {"greeting": greeting}


def register(api):
    # category "Examples"; icon_relpath points to icons/hello.png (optional)
    api.register_node(
        node_type="hello_world",
        node_class=HelloWorldNode,
        display_name="Hello World",
        description="Emit a greeting string for the given name",
        category="Examples",
        icon_relpath="icons/hello.png",
    )


