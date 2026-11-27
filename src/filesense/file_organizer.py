"""Quick Organize and custom rule pages."""

from .app_common import *


class FileOrganizerInterface(QWidget):
    def __init__(self, parent_window: "OrganizerWindow"):
        super().__init__()
        self.parent_window = parent_window
        self.monitored_folders: list[Path] = []
        self.conditions: list[ConditionRow] = []
        self.category_moves: list[tuple[Path, Path]] = []
        self.category_preview_rows: list[dict[str, object]] = []
        self.category_excluded_folders: list[Path] = []
        self.matches: list[Path] = []
        self.rule_preview_rows: list[dict[str, object]] = []
        self._build()

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 14)
        root.setSpacing(10)
        heading = TitleLabel("File Organizer")
        heading.setFont(QFont("Segoe UI", 14, QFont.Weight.DemiBold))
        root.addWidget(heading)

        self.tabs = TabWidget(self)
        self.tabs.setObjectName("sectionTabs")
        self.tabs.setTabsClosable(False)
        self.tabs.tabBar.setAddButtonVisible(False)
        self.tabs.tabBar.setCloseButtonDisplayMode(TabCloseButtonDisplayMode.NEVER)
        self.tabs.setTabMinimumWidth(190)
        self.tabs.setTabMaximumWidth(260)
        self.auto_page = self._build_auto_page()
        self.rule_page = self._build_rule_page()
        self.tabs.addTab(self.auto_page, "Quick Organize", FluentIcon.FOLDER)
        self.tabs.addTab(self.rule_page, "Build a rule", FluentIcon.EDIT)
        self._style_tabs()
        root.addWidget(self.tabs, 1)

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

    def _build_auto_page(self) -> QWidget:
        page = QWidget(self)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(9)
        folder_card = CardWidget(page)
        folder_layout = QHBoxLayout(folder_card)
        folder_layout.setContentsMargins(14, 9, 14, 9)
        folder_layout.addWidget(StrongBodyLabel("Folder"))
        self.category_path = LineEdit(folder_card)
        self.category_path.setPlaceholderText("Choose a folder to categorize")
        self.category_path.textChanged.connect(self._category_source_changed)
        folder_layout.addWidget(self.category_path, 1)
        browse = PushButton(FluentIcon.FOLDER, "Browse…", folder_card)
        browse.clicked.connect(lambda: self.choose_folder(self.category_path))
        folder_layout.addWidget(browse)
        layout.addWidget(folder_card)

        options_card = CardWidget(page)
        options_layout = QVBoxLayout(options_card)
        options_layout.setContentsMargins(14, 9, 14, 9)
        self.category_include_subfolders = CheckBox("Include subfolders", options_card)
        self.category_include_subfolders.setToolTip(
            "Off keeps the original behavior and organizes files only from the selected folder."
        )
        self.category_include_subfolders.toggled.connect(self._invalidate_category_preview)
        options_layout.addWidget(self.category_include_subfolders)
        excluded_header = QHBoxLayout()
        excluded_header.addWidget(StrongBodyLabel("Excluded folders"))
        excluded_header.addStretch(1)
        add_excluded = PushButton(FluentIcon.FOLDER_ADD, "Exclude folder…", options_card)
        add_excluded.clicked.connect(self.add_category_excluded_folder)
        self.remove_excluded = ToolButton(FluentIcon.DELETE, options_card)
        self.remove_excluded.setToolTip("Remove selected exclusions")
        self.remove_excluded.setAccessibleName("Remove selected excluded folders")
        self.remove_excluded.clicked.connect(self.remove_category_excluded_folders)
        excluded_header.addWidget(add_excluded)
        excluded_header.addWidget(self.remove_excluded)
        options_layout.addLayout(excluded_header)
        self.category_excluded_list = QListWidget(options_card)
        self.category_excluded_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.category_excluded_list.setMinimumHeight(42)
        self.category_excluded_list.setMaximumHeight(74)
        options_layout.addWidget(self.category_excluded_list)
        options_layout.addWidget(CaptionLabel(
            "Excluded folders are skipped when Include subfolders is enabled.", options_card
        ))
        layout.addWidget(options_card)

        self.category_table = make_table(
            ["Source full path", "Category", "Destination full path", "If destination exists"], page
        )
        self.category_table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.category_table.setWordWrap(False)
        self.category_table.setTextElideMode(Qt.TextElideMode.ElideNone)
        self.category_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.category_table.setColumnWidth(0, 520)
        self.category_table.setColumnWidth(1, 130)
        self.category_table.setColumnWidth(2, 520)
        self.category_table.setColumnWidth(3, 190)
        layout.addWidget(self.category_table, 1)
        buttons = QHBoxLayout()
        preview = PrimaryPushButton(FluentIcon.VIEW, "Preview", page)
        preview.clicked.connect(self.preview_categories)
        run = PrimaryPushButton(FluentIcon.PLAY, "Organize files", page)
        run.clicked.connect(self.run_categories)
        conflict_label = CaptionLabel("Default conflict action", page)
        self.category_conflict = NoScrollbarComboBox(page)
        self.category_conflict.addItems(CONFLICT_POLICIES)
        self.category_conflict.setCurrentText("Keep both")
        self.category_conflict.setFixedWidth(132)
        self.category_conflict.lock_height(30)
        self.category_conflict.currentTextChanged.connect(self._invalidate_category_preview)
        self.category_status = CaptionLabel("Choose a folder, then preview quick organization.")
        buttons.addWidget(preview)
        buttons.addWidget(run)
        buttons.addWidget(conflict_label)
        buttons.addWidget(self.category_conflict)
        buttons.addWidget(self.category_status, 1)
        layout.addLayout(buttons)
        return page

    def _build_rule_page(self) -> QWidget:
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        page = QWidget()
        page.setObjectName("ruleContent")
        page.setAutoFillBackground(True)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 6, 0)
        layout.setSpacing(9)

        monitor = CardWidget(page)
        monitor_layout = QVBoxLayout(monitor)
        monitor_layout.setContentsMargins(14, 11, 14, 11)
        monitor_layout.addWidget(StrongBodyLabel("Monitor"))
        monitor_layout.addWidget(CaptionLabel("Choose the folders to scan."))
        folder_row = QHBoxLayout()
        self.folder_list = QListWidget(monitor)
        self.folder_list.setMinimumHeight(54)
        self.folder_list.setMaximumHeight(78)
        folder_row.addWidget(self.folder_list, 1)
        folder_actions = QVBoxLayout()
        add_folder = PushButton(FluentIcon.FOLDER_ADD, "Add folder…", monitor)
        add_folder.clicked.connect(self.add_monitor_folder)
        remove_folder = ToolButton(FluentIcon.DELETE, monitor)
        remove_folder.setToolTip("Remove selected folders")
        remove_folder.setAccessibleName("Remove selected folders")
        remove_folder.setFixedSize(30, 30)
        remove_folder.clicked.connect(self.remove_monitor_folders)
        folder_actions.addWidget(add_folder)
        folder_actions.addWidget(remove_folder)
        folder_actions.addStretch(1)
        folder_row.addLayout(folder_actions)
        monitor_layout.addLayout(folder_row)
        self.include_subfolders = CheckBox("Include subfolders", monitor)
        monitor_layout.addWidget(self.include_subfolders)
        layout.addWidget(monitor)

        condition_card = CardWidget(page)
        condition_layout = QVBoxLayout(condition_card)
        condition_layout.setContentsMargins(14, 11, 14, 11)
        condition_layout.addWidget(StrongBodyLabel("If"))
        condition_layout.addWidget(CaptionLabel("Combine conditions with AND, OR, or NOT; they are evaluated from top to bottom."))
        self.condition_list = QVBoxLayout()
        self.condition_list.setContentsMargins(0, 0, 0, 0)
        self.condition_list.setSpacing(6)
        condition_layout.addLayout(self.condition_list)
        add_condition = PushButton("＋  Add condition", condition_card)
        add_condition.clicked.connect(self.add_condition)
        condition_layout.addWidget(add_condition, alignment=Qt.AlignmentFlag.AlignLeft)
        self.add_condition()

        then_card = CardWidget(page)
        then_layout = QVBoxLayout(then_card)
        then_layout.setContentsMargins(14, 11, 14, 11)
        then_layout.addWidget(StrongBodyLabel("Then"))
        then_layout.addWidget(CaptionLabel("Apply an action to matching files."))
        action_row = QHBoxLayout()
        self.action_combo = NoScrollbarComboBox(then_card)
        self.action_combo.addItems(["Move file", "Copy file", "Delete file"])
        action_row.addWidget(self.action_combo)
        self.destination = LineEdit(then_card)
        self.destination.setPlaceholderText("Choose a destination folder")
        action_row.addWidget(self.destination, 1)
        self.destination_browse = PushButton(FluentIcon.FOLDER, "Browse…", then_card)
        self.destination_browse.clicked.connect(lambda: self.choose_folder(self.destination))
        action_row.addWidget(self.destination_browse)
        then_layout.addLayout(action_row)
        conflict_row = QHBoxLayout()
        self.rule_conflict_label = CaptionLabel("Default conflict action", then_card)
        conflict_row.addWidget(self.rule_conflict_label)
        self.rule_conflict = NoScrollbarComboBox(then_card)
        self.rule_conflict.addItems(CONFLICT_POLICIES)
        self.rule_conflict.setCurrentText("Keep both")
        self.rule_conflict.setFixedWidth(132)
        self.rule_conflict.lock_height(30)
        conflict_row.addWidget(self.rule_conflict)
        conflict_row.addStretch(1)
        then_layout.addLayout(conflict_row)
        then_layout.addStretch(1)
        self.action_combo.currentTextChanged.connect(self.update_action_controls)
        self.update_action_controls(self.action_combo.currentText())
        rule_editors = QHBoxLayout()
        rule_editors.setSpacing(10)
        rule_editors.addWidget(condition_card, 3)
        rule_editors.addWidget(then_card, 2)
        layout.addLayout(rule_editors)

        action_row = QHBoxLayout()
        preview = PrimaryPushButton(FluentIcon.VIEW, "Preview matches", page)
        preview.clicked.connect(self.preview_rule)
        run = PrimaryPushButton(FluentIcon.PLAY, "Run rule", page)
        run.clicked.connect(self.run_rule)
        self.rule_status = CaptionLabel("Choose monitored folders to begin.")
        action_row.addWidget(preview)
        action_row.addWidget(run)
        action_row.addWidget(self.rule_status, 1)
        layout.addLayout(action_row)

        self.match_table = make_table(
            ["File name", "File type", "Size", "Source full path", "Destination full path", "If destination exists"], page
        )
        self.match_table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.match_table.setWordWrap(False)
        self.match_table.setTextElideMode(Qt.TextElideMode.ElideNone)
        self.match_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.match_table.setColumnWidth(0, 180)
        self.match_table.setColumnWidth(1, 115)
        self.match_table.setColumnWidth(2, 145)
        self.match_table.setColumnWidth(3, 520)
        self.match_table.setColumnWidth(4, 520)
        self.match_table.setColumnWidth(5, 190)
        self.match_table.setMinimumHeight(160)
        layout.addWidget(self.match_table, 1)
        scroll.setWidget(page)
        return scroll

    def choose_folder(self, line_edit: LineEdit) -> None:
        selected = QFileDialog.getExistingDirectory(self, "Choose folder", str(Path.home()))
        if selected:
            line_edit.setText(selected)

    def _category_source_changed(self, value: str) -> None:
        self._invalidate_category_preview()
        try:
            root = Path(value.strip()).expanduser().resolve()
        except OSError:
            root = None
        if root is None:
            kept = []
        else:
            kept = [path for path in self.category_excluded_folders if path.is_relative_to(root)]
        if kept != self.category_excluded_folders:
            self.category_excluded_folders = kept
            self.category_excluded_list.clear()
            self.category_excluded_list.addItems([str(path) for path in kept])

    def _invalidate_category_preview(self, *_args) -> None:
        if not hasattr(self, "category_table"):
            return
        self.category_moves.clear()
        self.category_preview_rows.clear()
        self.category_table.setRowCount(0)
        if hasattr(self, "category_status"):
            self.category_status.setText("Options changed; preview quick organization again.")

    def add_category_excluded_folder(self) -> None:
        source = Path(self.category_path.text().strip()).expanduser()
        if not source.is_dir():
            show_error(self, "Choose a source folder", "Choose the folder to organize before adding exclusions.")
            return
        selected = QFileDialog.getExistingDirectory(
            self, "Choose a folder to exclude", str(source)
        )
        if not selected:
            return
        root = source.resolve()
        excluded = Path(selected).resolve()
        if not excluded.is_relative_to(root):
            show_error(self, "Folder is outside the source", "Choose an excluded folder inside the source folder.")
            return
        if any(excluded == current or excluded.is_relative_to(current)
               for current in self.category_excluded_folders):
            return
        self.category_excluded_folders = [
            current for current in self.category_excluded_folders
            if not current.is_relative_to(excluded)
        ]
        self.category_excluded_folders.append(excluded)
        self.category_excluded_folders.sort(key=lambda path: str(path).casefold())
        self.category_excluded_list.clear()
        self.category_excluded_list.addItems([str(path) for path in self.category_excluded_folders])
        self._invalidate_category_preview()

    def remove_category_excluded_folders(self) -> None:
        selected = {item.text() for item in self.category_excluded_list.selectedItems()}
        if not selected:
            return
        self.category_excluded_folders = [
            path for path in self.category_excluded_folders if str(path) not in selected
        ]
        self.category_excluded_list.clear()
        self.category_excluded_list.addItems([str(path) for path in self.category_excluded_folders])
        self._invalidate_category_preview()

    def add_monitor_folder(self) -> None:
        selected = QFileDialog.getExistingDirectory(self, "Add monitored folder", str(Path.home()))
        if selected:
            path = Path(selected)
            if path not in self.monitored_folders:
                self.monitored_folders.append(path)
                self.folder_list.addItem(str(path))

    def remove_monitor_folders(self) -> None:
        for item in self.folder_list.selectedItems():
            index = self.folder_list.row(item)
            self.monitored_folders.pop(index)
            self.folder_list.takeItem(index)

    def add_condition(self) -> None:
        row: ConditionRow

        def remove() -> None:
            if len(self.conditions) <= 1:
                show_info(self, "At least one condition", "Keep at least one condition in the rule.")
                return
            self.conditions.remove(row)
            row.setParent(None)
            row.deleteLater()
            self.update_condition_connectors()

        row = ConditionRow(remove, self)
        self.conditions.append(row)
        self.condition_list.addWidget(row)
        self.update_condition_connectors()

    def update_condition_connectors(self) -> None:
        for index, row in enumerate(self.conditions):
            if index == 0:
                row.logic_operator.hide()
                row.logic_label.show()
            else:
                row.logic_label.hide()
                row.logic_operator.show()
                row.logic_operator.setEnabled(True)

    def update_action_controls(self, action: str) -> None:
        delete = action == "Delete file"
        self.destination.setEnabled(not delete)
        self.destination_browse.setEnabled(not delete)
        self.rule_conflict_label.setVisible(not delete)
        self.rule_conflict.setVisible(not delete)
        self.destination.setPlaceholderText("No destination needed for Delete" if delete else "Choose a destination folder")

    def preview_categories(self) -> None:
        self.category_moves.clear()
        self.category_preview_rows.clear()
        self.category_table.setRowCount(0)
        folder = Path(self.category_path.text().strip()).expanduser()
        if not folder.is_dir():
            show_error(self, "Choose a folder", "Choose a valid folder to preview Quick Organize.")
            return
        try:
            root = folder.resolve()
            # Use one canonical path for walking, exclusions, and preview paths.
            folder = root
            excluded = [path.resolve() for path in self.category_excluded_folders]
            invalid_exclusions = [path for path in excluded if not path.is_relative_to(root)]
            if invalid_exclusions:
                show_error(self, "Invalid excluded folder", "All excluded folders must be inside the selected source folder.")
                return
            missing_exclusions = [path for path in excluded if not path.is_dir()]
            if missing_exclusions:
                show_error(self, "Excluded folder not found", "Remove missing folders from the exclusion list and preview again.")
                return

            destinations: set[str] = set()
            requested_destinations: set[str] = set()
            conflict_policy = self.category_conflict.currentText()
            category_folder_names = {name.casefold() for name in CATEGORIES}

            def add_file(item: Path) -> None:
                category = next(
                    (name for name, extensions in CATEGORIES.items()
                     if item.suffix.casefold() in extensions),
                    None,
                )
                if not category:
                    return
                requested_destination = folder / category / item.name
                requested_key = os.path.normcase(str(requested_destination))
                conflict = requested_destination.exists() or requested_key in requested_destinations
                requested_destinations.add(requested_key)
                destination = requested_destination
                if conflict:
                    if conflict_policy == "Keep both":
                        destination = unique_conflict_path(destination, destinations)
                destinations.add(os.path.normcase(str(destination)))
                self.category_moves.append((item, requested_destination))
                row = self.category_table.rowCount()
                self.category_table.insertRow(row)
                for column, value in enumerate((
                    str(item), category, str(destination)
                )):
                    set_item(self.category_table, row, column, value)
                self.category_table.item(row, 0).setToolTip(str(item))
                self.category_table.item(row, 2).setToolTip(str(destination))
                policy = None
                if conflict:
                    policy = NoScrollbarComboBox(self.category_table)
                    policy.addItems(CONFLICT_POLICIES)
                    policy.setCurrentText(conflict_policy)
                    policy.setFixedWidth(180)
                    policy.lock_height(30)
                    self.category_table.setCellWidget(row, 3, policy)
                else:
                    set_item(self.category_table, row, 3, "—")
                self.category_preview_rows.append({
                    "row": row, "requested": requested_destination,
                    "conflict": conflict, "policy": policy,
                })
                if policy is not None:
                    policy.currentTextChanged.connect(self._refresh_category_conflict_preview)

            if self.category_include_subfolders.isChecked():
                def raise_scan_error(error):
                    raise error

                for current, directories, files in os.walk(folder, topdown=True, followlinks=False, onerror=raise_scan_error):
                    current_path = Path(current)
                    directories.sort(key=str.casefold)
                    files.sort(key=str.casefold)
                    directories[:] = [
                        name for name in directories
                        if not (current_path == folder and name.casefold() in category_folder_names)
                        and not (current_path / name).is_symlink()
                        and not any((current_path / name).resolve().is_relative_to(path) for path in excluded)
                    ]
                    if any(current_path.resolve().is_relative_to(path) for path in excluded):
                        continue
                    for name in files:
                        item = current_path / name
                        if item.is_file() and not item.is_symlink():
                            add_file(item)
            else:
                for item in sorted(folder.iterdir(), key=lambda path: path.name.casefold()):
                    if item.is_file() and not item.is_symlink():
                        add_file(item)
        except OSError as error:
            show_error(self, "Could not scan folder", str(error))
            return
        self._refresh_category_conflict_preview()
        self.category_table.resizeColumnToContents(0)
        self.category_table.resizeColumnToContents(2)
        self.category_status.setText(f"{len(self.category_moves)} file(s) ready for quick organization.")

    def _refresh_category_conflict_preview(self, *_args) -> None:
        reserved: set[str] = set()
        for entry in self.category_preview_rows:
            row = entry["row"]
            requested = entry["requested"]
            conflict = entry["conflict"]
            policy_widget = entry["policy"]
            policy = policy_widget.currentText() if policy_widget is not None else self.category_conflict.currentText()
            destination = requested
            if conflict and policy == "Keep both":
                destination = unique_conflict_path(requested, reserved)
            self.category_table.item(row, 2).setText(str(destination))
            self.category_table.item(row, 2).setToolTip(str(destination))
            reserved.add(os.path.normcase(str(destination)))
        self.category_table.resizeColumnToContents(0)
        self.category_table.resizeColumnToContents(2)

    def run_categories(self) -> None:
        if not self.category_moves:
            show_info(self, "Nothing to organize", "Preview Quick Organize first.")
            return
        default_policy = self.category_conflict.currentText()
        row_policies = [
            self.category_table.cellWidget(index, 3).currentText()
            if self.category_table.cellWidget(index, 3) is not None else default_policy
            for index in range(len(self.category_moves))
        ]
        replace_count = sum(
            bool(entry["conflict"]) and row_policies[index] == "Replace"
            for index, entry in enumerate(self.category_preview_rows)
        )
        message = f"Move {len(self.category_moves)} file(s) into their built-in category folders?"
        if replace_count:
            message += f"\n\nReplace will overwrite {replace_count} existing destination conflict(s). Continue?"
        elif default_policy == "Replace":
            message += "\n\nIf a destination conflict occurs, the existing file will be overwritten. Continue?"
        else:
            message += f"\n\nDefault action for destination conflicts: {default_policy}."
        if not confirm(self, "Organize files", message):
            return
        moved, skipped, errors = 0, 0, []
        for index, (source, requested_destination) in enumerate(self.category_moves):
            try:
                destination = requested_destination
                conflict_policy = row_policies[index]
                if os.path.normcase(str(source.resolve())) == os.path.normcase(str(destination.resolve())):
                    skipped += 1
                    continue
                if destination.exists():
                    if conflict_policy == "Skip":
                        skipped += 1
                        continue
                    if conflict_policy == "Replace":
                        pass
                    else:
                        destination = unique_conflict_path(destination)
                destination.parent.mkdir(parents=True, exist_ok=True)
                if conflict_policy == "Replace" and destination.exists():
                    move_with_replace(source, destination)
                else:
                    shutil.move(str(source), str(destination))
                moved += 1
            except OSError as error:
                errors.append(f"{source.name}: {error}")
        self.category_moves.clear()
        self.preview_categories()
        self.category_status.setText(
            f"Moved {moved}, skipped {skipped}." + (f" {len(errors)} failed." if errors else "")
        )
        self.parent_window.log_activity(
            "Quick Organize",
            f"Source: {self.category_path.text().strip()}; destination root: "
            f"{self.category_path.text().strip()}; moved {moved}, skipped {skipped}, failed {len(errors)}."
        )
        if errors:
            show_error(self, "Some files could not be moved", "\n".join(errors[:12]))
        else:
            show_info(self, "Organization complete", f"Moved {moved} file(s); skipped {skipped}.")

    def condition_matches(self, path: Path) -> bool:
        results = []
        for row in self.conditions:
            field = row.field.currentText()
            operator = row.operator.currentText()
            if field == "File Type":
                expected = row.type_value.currentText().strip()
                if not expected:
                    raise ValueError("Choose a file type for every File Type condition.")
                actual, wanted = file_type(path).casefold(), expected.casefold()
                matched = wanted in actual if operator == "Contains" else wanted not in actual if operator == "Does not contain" else actual == wanted if operator == "Is" else actual != wanted
            elif field == "File Extension":
                expected = row.value.text().strip()
                if not expected:
                    raise ValueError("Enter a value for every condition.")
                actual, wanted = path.name.casefold(), expected.casefold()
                if not wanted.startswith("."):
                    wanted = "." + wanted
                matched = wanted in actual if operator == "Contains" else wanted not in actual if operator == "Does not contain" else actual.endswith(wanted) if operator == "Is" else not actual.endswith(wanted)
            elif field == "File Size":
                expected = row.value.text().strip()
                if not expected:
                    raise ValueError("Enter a value for every condition.")
                try:
                    limit = float(expected) * SIZE_UNITS[row.unit.currentText()]
                except ValueError as error:
                    raise ValueError("File Size conditions need a numeric value.") from error
                size = path.stat().st_size
                matched = {
                    "Is": size == limit, "Is not": size != limit,
                    "Greater than": size > limit, "Less than": size < limit,
                    "At least": size >= limit, "At most": size <= limit,
                }[operator]
            elif field == "File Name":
                expected = row.value.text().strip().casefold()
                if not expected:
                    raise ValueError("Enter a value for every condition.")
                actual = path.name.casefold()
                matched = {
                    "Contains": expected in actual,
                    "Does not contain": expected not in actual,
                    "Starts with": actual.startswith(expected),
                    "Ends with": actual.endswith(expected),
                    "Matches exact text": actual == expected,
                    "Matches pattern (advanced)": fnmatch.fnmatchcase(actual, expected),
                }[operator]
            else:  # File Date
                stat = path.stat()
                timestamp = {
                    "Date created": stat.st_ctime,
                    "Date modified": stat.st_mtime,
                    "Date last accessed": stat.st_atime,
                }[row.name_date.currentText()]
                actual_date = datetime.fromtimestamp(timestamp)
                if operator in ("Before", "After", "Between"):
                    start = datetime.strptime(row.date_start.date().toString("yyyy-MM-dd"), "%Y-%m-%d").date()
                    if operator == "Before":
                        matched = actual_date.date() < start
                    elif operator == "After":
                        matched = actual_date.date() > start
                    else:
                        end = datetime.strptime(row.date_end.date().toString("yyyy-MM-dd"), "%Y-%m-%d").date()
                        if end < start:
                            raise ValueError("The end date must be the same as or later than the start date.")
                        matched = start <= actual_date.date() <= end
                else:
                    amount = row.date_period.value()
                    unit_days = {"Days": 1, "Months": 30, "Years": 365}[row.date_period_unit.currentText()]
                    cutoff = datetime.now() - timedelta(days=amount * unit_days)
                    matched = {
                        "Within last": cutoff <= actual_date <= datetime.now(),
                        "Older than": actual_date < cutoff,
                        "Newer than": actual_date > cutoff,
                    }[operator]
            results.append(matched)
        if not results:
            return True
        result = results[0]
        for index in range(1, len(results)):
            if self.conditions[index].logic_operator.currentText() == "AND":
                result = result and results[index]
            elif self.conditions[index].logic_operator.currentText() == "OR":
                result = result or results[index]
            else:  # NOT means AND NOT for this condition.
                result = result and not results[index]
        return result

    def iter_monitored_files(self):
        seen: set[str] = set()
        for root in self.monitored_folders:
            if not root.is_dir():
                continue
            if self.include_subfolders.isChecked():
                for current, dirs, files in os.walk(root, followlinks=False):
                    dirs[:] = [name for name in dirs if name.casefold() != DUPLICATES_FOLDER.casefold()]
                    candidates = (Path(current) / name for name in files)
                    for path in candidates:
                        key = os.path.normcase(str(path.resolve()))
                        if key not in seen:
                            seen.add(key)
                            yield path
            else:
                for path in root.iterdir():
                    if path.is_file():
                        key = os.path.normcase(str(path.resolve()))
                        if key not in seen:
                            seen.add(key)
                            yield path

    def preview_rule(self) -> None:
        self.matches.clear()
        self.rule_preview_rows.clear()
        self.match_table.setRowCount(0)
        if not self.monitored_folders:
            show_error(self, "No monitored folders", "Add at least one folder in the Monitor section.")
            return
        if self.action_combo.currentText() != "Delete file" and not self.destination.text().strip():
            show_error(self, "Choose a destination", "Choose a destination folder for Move file or Copy file.")
            return
        action = self.action_combo.currentText()
        target = Path(self.destination.text().strip()).expanduser() if action != "Delete file" else None
        conflict_policy = self.rule_conflict.currentText()
        reserved_destinations: set[str] = set()
        requested_destinations: set[str] = set()
        try:
            for path in sorted(self.iter_monitored_files(), key=lambda item: str(item).casefold()):
                if self.condition_matches(path):
                    self.matches.append(path)
                    destination_text = "—"
                    conflict_action = "—"
                    requested_destination = None
                    same_source = False
                    conflict = False
                    if target is not None:
                        requested_destination = target / path.name
                        same_source = os.path.normcase(str(path.resolve())) == os.path.normcase(
                            str(requested_destination.resolve())
                        )
                        destination_key = os.path.normcase(str(requested_destination.resolve()))
                        conflict = requested_destination.exists() or destination_key in requested_destinations
                        requested_destinations.add(destination_key)
                        destination = requested_destination
                        if same_source:
                            conflict_action = "Already in destination"
                        elif conflict:
                            if conflict_policy == "Keep both":
                                destination = unique_conflict_path(destination, reserved_destinations)
                                conflict_action = conflict_policy
                            elif conflict_policy == "Skip":
                                conflict_action = "Skip"
                            else:
                                conflict_action = "Replace (confirm)"
                        reserved_destinations.add(os.path.normcase(str(destination.resolve())))
                        destination_text = str(destination)
                    row = self.match_table.rowCount()
                    self.match_table.insertRow(row)
                    for column, value in enumerate((
                        path.name, file_type(path), f"{path.stat().st_size:,} bytes", str(path),
                        destination_text, conflict_action,
                    )):
                        set_item(self.match_table, row, column, value)
                    self.match_table.item(row, 3).setToolTip(str(path))
                    if requested_destination is not None:
                        self.match_table.item(row, 4).setToolTip(destination_text)
                    policy_widget = None
                    if conflict and not same_source:
                        policy_widget = NoScrollbarComboBox(self.match_table)
                        policy_widget.addItems(CONFLICT_POLICIES)
                        policy_widget.setCurrentText(conflict_policy)
                        policy_widget.setFixedWidth(180)
                        policy_widget.lock_height(30)
                        self.match_table.takeItem(row, 5)
                        self.match_table.setCellWidget(row, 5, policy_widget)
                        policy_widget.currentTextChanged.connect(self._refresh_rule_conflict_preview)
                    self.rule_preview_rows.append({
                        "row": row, "source": path, "requested": requested_destination,
                        "same_source": same_source, "conflict": conflict, "policy": policy_widget,
                    })
        except (OSError, ValueError) as error:
            show_error(self, "Could not preview rule", str(error))
            return
        self._refresh_rule_conflict_preview()
        self.match_table.resizeColumnToContents(3)
        self.match_table.resizeColumnToContents(4)
        self.rule_status.setText(f"{len(self.matches)} file(s) match the rule.")

    def _refresh_rule_conflict_preview(self, *_args) -> None:
        reserved: set[str] = set()
        for entry in self.rule_preview_rows:
            row = entry["row"]
            requested = entry["requested"]
            if requested is None:
                continue
            policy_widget = entry["policy"]
            policy = policy_widget.currentText() if policy_widget is not None else self.rule_conflict.currentText()
            destination = requested
            if entry["conflict"] and not entry["same_source"] and policy == "Keep both":
                destination = unique_conflict_path(requested, reserved)
            if entry["same_source"]:
                conflict_text = "Already in destination"
            elif entry["conflict"] and policy_widget is None:
                conflict_text = "—"
            else:
                conflict_text = "—"
            self.match_table.item(row, 4).setText(str(destination))
            self.match_table.item(row, 4).setToolTip(str(destination))
            if policy_widget is None:
                self.match_table.item(row, 5).setText(conflict_text)
            reserved.add(os.path.normcase(str(destination.resolve())))
        self.match_table.resizeColumnToContents(3)
        self.match_table.resizeColumnToContents(4)

    def run_rule(self) -> None:
        saved_row_policies = {
            os.path.normcase(str(entry["source"].resolve())): entry["policy"].currentText()
            for entry in self.rule_preview_rows
            if entry["policy"] is not None
        }
        self.preview_rule()
        if not self.matches:
            return
        for entry in self.rule_preview_rows:
            source_key = os.path.normcase(str(entry["source"].resolve()))
            policy_widget = entry["policy"]
            if policy_widget is not None and source_key in saved_row_policies:
                policy_widget.setCurrentText(saved_row_policies[source_key])
        self._refresh_rule_conflict_preview()

        action = self.action_combo.currentText()
        default_policy = self.rule_conflict.currentText()
        row_policies = {
            os.path.normcase(str(entry["source"].resolve())): (
                entry["policy"].currentText() if entry["policy"] is not None else default_policy
            )
            for entry in self.rule_preview_rows
        }
        replace_count = sum(
            entry["conflict"] and not entry["same_source"]
            and row_policies[os.path.normcase(str(entry["source"].resolve()))] == "Replace"
            for entry in self.rule_preview_rows
        )
        if action == "Delete file":
            prompt = f"Send {len(self.matches)} file(s) to the Windows Recycle Bin?"
        else:
            prompt = f"{action} {len(self.matches)} file(s) to:\n{self.destination.text()}?"
            if replace_count:
                prompt += f"\n\nReplace will overwrite {replace_count} existing destination conflict(s). Continue?"
            elif default_policy == "Replace":
                prompt += "\n\nIf a destination conflict occurs, the existing file will be overwritten. Continue?"
            else:
                prompt += f"\n\nDefault action for destination conflicts: {default_policy}."
        if not confirm(self, "Run rule", prompt):
            return
        moved = copied = deleted = skipped = 0
        errors: list[str] = []
        target = Path(self.destination.text().strip()).expanduser()
        for source in self.matches:
            try:
                if action == "Delete file":
                    send_to_recycle_bin(source)
                    deleted += 1
                else:
                    source_key = os.path.normcase(str(source.resolve()))
                    conflict_policy = row_policies.get(source_key, default_policy)
                    destination = target / source.name
                    same_source = os.path.normcase(str(source.resolve())) == os.path.normcase(
                        str(destination.resolve())
                    )
                    if same_source:
                        skipped += 1
                        continue
                    if destination.exists():
                        if conflict_policy == "Skip":
                            skipped += 1
                            continue
                        if conflict_policy == "Keep both":
                            destination = unique_conflict_path(destination)
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    if action == "Move file":
                        if conflict_policy == "Replace" and destination.exists():
                            move_with_replace(source, destination)
                        else:
                            shutil.move(str(source), str(destination))
                        moved += 1
                    else:
                        shutil.copy2(source, destination)
                        copied += 1
            except (OSError, AttributeError) as error:
                errors.append(f"{source.name}: {error}")
        summary = f"Moved {moved}, copied {copied}, skipped {skipped}, sent to Recycle Bin {deleted}."
        self.rule_status.setText(summary + (f" {len(errors)} failed." if errors else ""))
        self.parent_window.log_activity(
            f"Build rule: {action}",
            f"Source folders: {'; '.join(str(root) for root in self.monitored_folders)}; "
            f"destination: {self.destination.text().strip() if action != 'Delete file' else 'Recycle Bin'}; "
            f"{summary} Failed: {len(errors)}."
        )
        if errors:
            show_error(self, "Rule finished with errors", summary + "\n\n" + "\n".join(errors[:12]))
        else:
            show_info(self, "Rule complete", summary)
        self.preview_rule()


