class ConfigBinder:
    @staticmethod
    def bind_radio_group(vm, group, path, on_after_changed=None):
        def on_changed(btn):
            value = btn.property("tag_value")
            vm.set_config(path, value)
            if on_after_changed:
                on_after_changed(value)

        group.buttonClicked.connect(on_changed)

    @staticmethod
    def bind_line_edit(vm, edit, path: str):
        def on_changed(text):
            vm.set_config(path, text)

        edit.textChanged.connect(on_changed)

    @staticmethod
    def bind_combo(vm, combo, path: str):
        def on_changed():
            vm.set_config(path, combo.currentData())

        combo.currentIndexChanged.connect(on_changed)

    @staticmethod
    def bind_checkbox(vm, checkbox, path: str):
        def on_changed(checked):
            vm.set_config(path, bool(checked))

        checkbox.toggled.connect(on_changed)

    @staticmethod
    def bind_spinbox(vm, spinbox, path: str):
        def on_changed(value: int):
            vm.set_config(path, int(value))

        spinbox.valueChanged.connect(on_changed)

    @staticmethod
    def bind_slider(vm, slider, path: str):
        def on_changed(value: int):
            vm.set_config(path, int(value))

        slider.valueChanged.connect(on_changed)
