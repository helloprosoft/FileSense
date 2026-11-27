"""Duplicate file discovery and cleanup page."""

from .app_common import *


class DuplicateFinderInterface(QWidget):
    def __init__(self, parent_window: "OrganizerWindow"):
        super().__init__()
        self.parent_window = parent_window
        self.scans: dict[str, dict[str, object]] = {
            "find": {"groups": [], "keepers": {}, "roots": []},
            "rule": {"groups": [], "keepers": {}, "roots": []},
        }
        self.find_folders: list[Path] = []
        self.rule_folders: list[Path] = []
        self.rule_conditions: list[ConditionRow] = []
        self._build()

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 14)
        layout.setSpacing(10)
        heading = TitleLabel("Duplicate Finder")
        heading.setFont(QFont("Segoe UI", 14, QFont.Weight.DemiBold))
        layout.addWidget(heading)
        self.tabs = TabWidget(self)
        self.tabs.setObjectName("sectionTabs")
        self.tabs.setTabsClosable(False)
        self.tabs.tabBar.setAddButtonVisible(False)
        self.tabs.tabBar.setCloseButtonDisplayMode(TabCloseButtonDisplayMode.NEVER)
        self.tabs.setTabMinimumWidth(190)
        self.tabs.setTabMaximumWidth(260)
        self.find_tab = self._build_find_tab()
        self.rule_tab = self._build_duplicate_rule_tab()
        self.tabs.addTab(self.find_tab, "Find duplicates", FluentIcon.SEARCH)
        self.tabs.addTab(self.rule_tab, "Build a rule", FluentIcon.EDIT)
        self._style_tabs()
        layout.addWidget(self.tabs, 1)

    def _style_tabs(self) -> None:
        dark = getattr(self.window(), "appearance", "Light") == "Dark"
        selected = QColor(ACCENT_COLOR)
        text = QColor("#F7F7F7" if dark else "#2B2118")
        self.tabs.setTabSelectedBackgroundColor(selected, selected)
        self.tabs.tabBar.itemLayout.setContentsMargins(0, 5, 0, 5)
        for index in range(self.tabs.count()):
            item = self.tabs.tabBar.items[index]
            item.setFixedHeight(36)
            item.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
            align_tab_icon(item)
            self.tabs.setTabTextColor(index, text)

    def _build_folder_picker(self, parent: QWidget, folders: list[Path], title: str) -> tuple[QWidget, QListWidget]:
        card = CardWidget(parent)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.addWidget(StrongBodyLabel(title))
        row = QHBoxLayout()
        folder_list = QListWidget(card)
        folder_list.setMinimumHeight(50)
        folder_list.setMaximumHeight(72)
        row.addWidget(folder_list, 1)
        buttons = QVBoxLayout()
        add_button = PushButton(FluentIcon.FOLDER_ADD, "Add folder…", card)
        add_button.clicked.connect(lambda: self.add_folder(folders, folder_list))
        remove_button = ToolButton(FluentIcon.DELETE, card)
        remove_button.setToolTip("Remove selected folders")
        remove_button.setAccessibleName("Remove selected folders")
        remove_button.setFixedSize(30, 30)
        remove_button.clicked.connect(lambda: self.remove_folders(folders, folder_list))
        buttons.addWidget(add_button)
        buttons.addWidget(remove_button)
        buttons.addStretch(1)
        row.addLayout(buttons)
        layout.addLayout(row)
        return card, folder_list

    def _build_results(self, parent: QWidget, mode: str) -> tuple[QTreeWidget, CaptionLabel]:
        tree = QTreeWidget(parent)
        tree.setHeaderLabels(["Name / Group", "Keep", "Type", "Size", "Size comparison", "Location"])
        tree.setAlternatingRowColors(True)
        tree.setSelectionMode(QTreeWidget.SelectionMode.SingleSelection)
        tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        tree.header().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        tree.header().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        tree.header().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        tree.header().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        tree.header().setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)
        tree.headerItem().setToolTip(4, "Same file size does not necessarily mean identical file contents.")
        return tree, CaptionLabel("Add folders to compare duplicate names.", parent)

    def _build_result_actions(self, parent: QWidget, mode: str, tree: QTreeWidget, status: CaptionLabel) -> QHBoxLayout:
        actions = QHBoxLayout()
        scan = PrimaryPushButton(FluentIcon.SEARCH, "Scan for duplicates", parent)
        scan.clicked.connect(lambda: self.scan(mode))
        apply_selection = PrimaryPushButton(FluentIcon.DELETE, "Keep checked; delete unchecked", parent)
        apply_selection.clicked.connect(lambda: self.resolve(mode))
        actions.addWidget(scan)
        actions.addWidget(apply_selection)
        actions.addWidget(status, 1)
        return actions

    def _build_find_tab(self) -> QWidget:
        page = QWidget(self)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 8, 0, 0)
        layout.setSpacing(10)
        folder_card, self.find_folder_list = self._build_folder_picker(page, self.find_folders, "Folders to compare")
        layout.addWidget(folder_card)
        self.find_include_subfolders = CheckBox("Include subfolders", page)
        layout.addWidget(self.find_include_subfolders)
        layout.addWidget(CaptionLabel("Same-name files show their sizes for comparison. Equal sizes do not guarantee identical contents."))
        self.find_tree, self.find_status = self._build_results(page, "find")
        layout.addWidget(self.find_tree, 1)
        layout.addLayout(self._build_result_actions(page, "find", self.find_tree, self.find_status))
        return page

    def _build_duplicate_rule_tab(self) -> QWidget:
        page = QWidget(self)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 8, 0, 0)
        layout.setSpacing(10)
        folder_card, self.rule_folder_list = self._build_folder_picker(page, self.rule_folders, "Folders to monitor")
        layout.addWidget(folder_card)
        self.rule_include_subfolders = CheckBox("Include subfolders", page)
        layout.addWidget(self.rule_include_subfolders)

        condition = CardWidget(page)
        condition_layout = QVBoxLayout(condition)
        condition_layout.setContentsMargins(16, 12, 16, 12)
        condition_layout.addWidget(StrongBodyLabel("If"))
        condition_layout.addWidget(CaptionLabel(
            "Filter duplicate files by type or extension. Combine conditions in order with AND, OR, or NOT."
        ))
        self.rule_condition_layout = QVBoxLayout()
        self.rule_condition_layout.setSpacing(6)
        condition_layout.addLayout(self.rule_condition_layout)
        add_condition = PushButton(FluentIcon.ADD, "Add condition", condition)
        add_condition.clicked.connect(self.add_rule_condition)
        condition_layout.addWidget(add_condition, alignment=Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(condition)
        self.add_rule_condition()

        self.rule_tree, self.rule_status = self._build_results(page, "rule")
        layout.addWidget(self.rule_tree, 1)
        layout.addLayout(self._build_result_actions(page, "rule", self.rule_tree, self.rule_status))
        return page

    def add_rule_condition(self) -> None:
        row: ConditionRow

        def remove() -> None:
            if len(self.rule_conditions) <= 1:
                show_info(self, "At least one condition", "Keep at least one condition in the duplicate rule.")
                return
            self.rule_conditions.remove(row)
            row.setParent(None)
            row.deleteLater()
            self.update_rule_connectors()

        row = ConditionRow(remove, self, fields=("File Type", "File Extension"))
        row.field.setCurrentText("File Type")
        self.rule_conditions.append(row)
        self.rule_condition_layout.addWidget(row)
        self.update_rule_connectors()

    def update_rule_connectors(self) -> None:
        for index, row in enumerate(self.rule_conditions):
            if index == 0:
                row.logic_operator.hide()
                row.logic_label.show()
            else:
                row.logic_label.hide()
                row.logic_operator.show()

    def add_folder(self, folders: list[Path], folder_list: QListWidget) -> None:
        selected = QFileDialog.getExistingDirectory(self, "Add folder to compare", str(Path.home()))
        if selected:
            path = Path(selected)
            if path not in folders:
                folders.append(path)
                folder_list.addItem(str(path))

    def remove_folders(self, folders: list[Path], folder_list: QListWidget) -> None:
        selected_rows = sorted({folder_list.row(item) for item in folder_list.selectedItems()}, reverse=True)
        for index in selected_rows:
            folders.pop(index)
            folder_list.takeItem(index)

    def scan(self, mode: str) -> None:
        folders = self.find_folders if mode == "find" else self.rule_folders
        tree = self.find_tree if mode == "find" else self.rule_tree
        status = self.find_status if mode == "find" else self.rule_status
        state = self.scans[mode]
        tree.clear()
        state["groups"] = []
        state["keepers"] = {}
        if not folders:
            show_error(self, "No folders selected", "Add at least one folder to scan for duplicates.")
            return
        include_subfolders = self.find_include_subfolders.isChecked() if mode == "find" else self.rule_include_subfolders.isChecked()
        if mode == "rule":
            try:
                self.validate_rule()
            except ValueError as error:
                show_error(self, "Complete the duplicate rule", str(error))
                return

        grouped: dict[tuple[str, bool], list[Path]] = defaultdict(list)
        seen: set[str] = set()
        errors: list[str] = []

        def on_error(error: OSError) -> None:
            errors.append(str(error))

        for root in folders:
            if not root.is_dir():
                errors.append(f"Folder not found: {root}")
                continue
            for current, dirs, files in os.walk(root, topdown=True, onerror=on_error, followlinks=False):
                current_path = Path(current)
                if not include_subfolders and current_path != root:
                    dirs[:] = []
                    continue
                try:
                    relative = current_path.relative_to(root)
                except ValueError:
                    continue
                if relative.parts and relative.parts[0].casefold() == DUPLICATES_FOLDER.casefold():
                    dirs[:] = []
                    continue
                dirs[:] = [name for name in dirs if name.casefold() != DUPLICATES_FOLDER.casefold()]
                candidates = [(current_path / name, True) for name in dirs]
                candidates.extend((current_path / name, False) for name in files)
                if not include_subfolders:
                    dirs[:] = []
                for path, is_folder in candidates:
                    key = os.path.normcase(str(path.resolve()))
                    if key in seen:
                        continue
                    seen.add(key)
                    if mode == "rule":
                        # Type and extension rules apply to files; folders are still
                        # available in the unrestricted Find duplicates tab.
                        if is_folder or not self.duplicate_rule_matches(path):
                            continue
                    grouped[(path.name.casefold(), is_folder)].append(path)

        groups = [sorted(items, key=lambda item: str(item).casefold()) for items in grouped.values() if len(items) > 1]
        groups.sort(key=lambda items: (items[0].name.casefold(), items[0].is_dir()))
        state["groups"] = groups
        state["roots"] = list(folders)
        for index, paths in enumerate(groups):
            is_file_group = not paths[0].is_dir()
            try:
                sizes = [path.stat().st_size for path in paths] if is_file_group else []
                size_comparison = "Same size" if sizes and len(set(sizes)) == 1 else "Different sizes" if sizes else "—"
            except OSError:
                sizes = []
                size_comparison = "Could not read sizes"
            group_item = QTreeWidgetItem(tree, [f"{paths[0].name} ({len(paths)} entries)", "", "Group", "", size_comparison, ""])
            for path in paths:
                try:
                    size = format_file_size(path) if path.is_file() else "—"
                except OSError:
                    size = "Unavailable"
                child = QTreeWidgetItem(group_item, [path.name, "", "Folder" if path.is_dir() else "File", size, "", str(path)])
                child.setFlags(child.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                child.setCheckState(1, Qt.CheckState.Unchecked)
                child.setData(0, Qt.ItemDataRole.UserRole, (index, str(path)))
            group_item.setExpanded(True)
        group_count = len(groups)
        entry_count = sum(len(group) for group in groups)
        status.setText(f"Found {group_count} group(s), {entry_count} entries." if group_count else "No matching duplicate names found.")
        scan_description = (
            f"Mode: {'Build a rule' if mode == 'rule' else 'Find duplicates'}; "
            f"folders: {'; '.join(str(root) for root in folders)}; "
            f"subfolders: {'included' if include_subfolders else 'not included'}; "
        )
        if mode == "rule":
            scan_description += "conditions: " + self.rule_description() + "; "
        scan_description += (
            f"found {group_count} duplicate group(s) / {entry_count} entries; "
            f"scan errors: {len(errors)}."
        )
        self.parent_window.log_activity("Duplicate scan", scan_description)
        if errors:
            show_info(self, "Some folders could not be scanned", "\n".join(errors[:10]))

    def validate_rule(self) -> None:
        if not self.rule_conditions:
            raise ValueError("Add at least one condition.")
        for row in self.rule_conditions:
            field = row.field.currentText()
            if field == "File Type" and not row.type_value.currentText().strip():
                raise ValueError("Choose a file type for every File Type condition.")
            if field == "File Extension" and not row.value.text().strip():
                raise ValueError("Enter an extension for every File Extension condition.")

    def duplicate_rule_matches(self, path: Path) -> bool:
        results: list[bool] = []
        for row in self.rule_conditions:
            field = row.field.currentText()
            operator = row.operator.currentText()
            if field == "File Type":
                actual = file_type(path).casefold()
                expected = row.type_value.currentText().strip().casefold()
                matched = {
                    "Is": actual == expected,
                    "Is not": actual != expected,
                    "Contains": expected in actual,
                    "Does not contain": expected not in actual,
                }[operator]
            else:
                actual = path.name.casefold()
                expected = row.value.text().strip().casefold()
                if not expected.startswith("."):
                    expected = "." + expected
                matched = {
                    "Is": actual.endswith(expected),
                    "Is not": not actual.endswith(expected),
                    "Contains": expected in actual,
                    "Does not contain": expected not in actual,
                }[operator]
            results.append(matched)

        result = results[0]
        for index in range(1, len(results)):
            connector = self.rule_conditions[index].logic_operator.currentText()
            if connector == "AND":
                result = result and results[index]
            elif connector == "OR":
                result = result or results[index]
            else:  # NOT combines this condition as AND NOT.
                result = result and not results[index]
        return result

    def rule_description(self) -> str:
        parts = []
        for index, row in enumerate(self.rule_conditions):
            field = row.field.currentText()
            value = row.type_value.currentText() if field == "File Type" else row.value.text().strip()
            if index:
                parts.append(row.logic_operator.currentText())
            parts.append(f"{field} {row.operator.currentText()} {value}")
        return " ".join(parts)

    def resolve(self, mode: str) -> None:
        state = self.scans[mode]
        groups: list[list[Path]] = state["groups"]
        tree = self.find_tree if mode == "find" else self.rule_tree
        keepers: list[Path] = []
        paths_to_delete: list[Path] = []
        for group_index, group in enumerate(groups):
            group_item = tree.topLevelItem(group_index)
            for child_index, path in enumerate(group):
                child = group_item.child(child_index)
                if child.checkState(1) == Qt.CheckState.Checked:
                    keepers.append(path)
                else:
                    paths_to_delete.append(path)
        if not paths_to_delete:
            show_info(self, "Nothing to delete", "Every duplicate entry is marked to keep.")
            return
        for source in paths_to_delete:
            if source.is_dir() and any(source != keeper and source in keeper.parents for keeper in keepers):
                show_info(self, "Review folder choices", f"The folder selected for deletion contains an entry selected to keep:\n{source}\n\nMark this folder to keep, or uncheck the nested entry.")
                return
        if keepers:
            prompt = f"Keep {len(keepers)} checked entr(y/ies) and send {len(paths_to_delete)} unchecked entr(y/ies) to the Windows Recycle Bin?"
        else:
            prompt = f"No entries are checked to keep. Send all {len(paths_to_delete)} duplicate entr(y/ies) to the Windows Recycle Bin?"
        if not confirm(self, "Apply keep selection", prompt):
            return
        deleted, errors = 0, []
        for source in sorted(paths_to_delete, key=lambda path: len(path.parts), reverse=True):
            try:
                if not source.exists():
                    continue
                send_to_recycle_bin(source)
                deleted += 1
            except (OSError, AttributeError) as error:
                errors.append(f"{source}: {error}")
        status = self.find_status if mode == "find" else self.rule_status
        status.setText(f"Kept {len(keepers)} entr(y/ies); sent {deleted} to the Recycle Bin." + (f" {len(errors)} failed." if errors else ""))
        if errors:
            show_error(self, "Some entries could not be deleted", "\n".join(errors[:12]))
        else:
            show_info(self, "Selection applied", f"Kept {len(keepers)} entr(y/ies) and sent {deleted} entr(y/ies) to the Windows Recycle Bin.")
        self.parent_window.log_activity(
            "Resolve duplicates",
            f"Mode: {'Build a rule' if mode == 'rule' else 'Find duplicates'}; kept {len(keepers)} "
            f"entry/entries; sent {deleted} to Recycle Bin; failed {len(errors)}. Removed paths: "
            + ("; ".join(str(path) for path in deleted) if deleted else "none")
        )
        self.scan(mode)


