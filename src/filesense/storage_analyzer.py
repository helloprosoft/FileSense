"""Storage Analyzer page."""

from .app_common import *


class StorageAnalyzerInterface(QWidget):
    def __init__(self, parent_window: "OrganizerWindow"):
        super().__init__()
        self.parent_window = parent_window
        self.selected_root: Path | None = None
        self.worker: StorageScanWorker | None = None
        self.root_node: StorageNode | None = None
        self.extension_stats: dict[str, ExtensionStats] = {}
        self.scan_errors = 0
        self.scan_directories = 0
        self.drive_paths: dict[str, Path] = {}
        self.icon_provider = QFileIconProvider()
        self.folder_icon = self.icon_provider.icon(QFileIconProvider.IconType.Folder)
        self.file_icon = self.icon_provider.icon(QFileIconProvider.IconType.File)
        self._build()

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 14)
        layout.setSpacing(10)
        heading = TitleLabel("Storage Analyzer")
        heading.setFont(QFont("Segoe UI", 14, QFont.Weight.DemiBold))
        layout.addWidget(heading)
        layout.addWidget(CaptionLabel("See which folders use the most space."))

        source_card = CardWidget(self)
        source_row = QHBoxLayout(source_card)
        source_row.setContentsMargins(14, 10, 14, 10)
        source_row.setSpacing(8)
        self.drive_combo = NoScrollbarComboBox(source_card)
        self.drive_combo.setPlaceholderText("Select a drive")
        self._load_drives()
        self.drive_combo.currentTextChanged.connect(self._select_drive)
        source_row.addWidget(self.drive_combo, 1)
        browse = PushButton(FluentIcon.FOLDER, "Choose folder…", source_card)
        browse.setFixedHeight(30)
        browse.clicked.connect(self._choose_folder)
        source_row.addWidget(browse)
        self.scan_button = PrimaryPushButton(FluentIcon.SEARCH, "Scan storage", source_card)
        self.scan_button.setFixedHeight(30)
        self.scan_button.clicked.connect(self._start_scan)
        source_row.addWidget(self.scan_button)
        self.fast_scan = CheckBox("Fast NTFS scan", source_card)
        self.fast_scan.setToolTip(
            "Use Windows batched directory enumeration on NTFS volumes. This reduces per-file metadata calls; "
            "it is not a direct Master File Table scan and does not require administrator rights."
        )
        self.fast_scan.setChecked(True)
        source_row.addWidget(self.fast_scan)
        layout.addWidget(source_card)

        self.location_status = CaptionLabel("Select a drive or choose a folder to begin.")
        layout.addWidget(self.location_status)
        self.progress = QProgressBar(self)
        self.progress.setRange(0, 0)
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(8)
        self.progress.hide()
        layout.addWidget(self.progress)

        splitter = QSplitter(Qt.Orientation.Horizontal, self)
        folder_panel = QWidget(splitter)
        folder_layout = QVBoxLayout(folder_panel)
        folder_layout.setContentsMargins(0, 0, 4, 0)
        folder_layout.setSpacing(6)
        folder_heading = QHBoxLayout()
        folder_heading.addWidget(StrongBodyLabel("Folder breakdown"))
        folder_heading.addStretch(1)
        self.delete_folder_button = PushButton(FluentIcon.DELETE, "Delete selected", folder_panel)
        self.delete_folder_button.setFixedHeight(30)
        self.delete_folder_button.setToolTip("Send the selected folder and its contents to the Recycle Bin")
        self.delete_folder_button.setEnabled(False)
        self.delete_folder_button.clicked.connect(self._delete_selected_folder)
        folder_heading.addWidget(self.delete_folder_button)
        folder_layout.addLayout(folder_heading)
        self.tree = QTreeWidget(folder_panel)
        self.tree.setHeaderLabels(["Name", "Size", "Allocated", "Files", "Folders", "% of parent"])
        self.tree.setAlternatingRowColors(True)
        self.tree.setUniformRowHeights(True)
        self.tree.setAnimated(False)
        self.tree.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.tree.setMinimumHeight(260)
        self.tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for column in range(1, 6):
            self.tree.header().setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
        self.tree.header().setStretchLastSection(False)
        self.tree.headerItem().setToolTip(1, "Total logical file size in this folder and its subfolders.")
        self.tree.headerItem().setToolTip(
            2, "Allocated size is estimated from the volume allocation unit for regular files."
        )
        self.tree.itemExpanded.connect(self._expand_storage_item)
        self.tree.itemSelectionChanged.connect(self._storage_selection_changed)
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._show_storage_context_menu)
        folder_layout.addWidget(self.tree, 1)
        folder_layout.addWidget(CaptionLabel("Ctrl/Shift-select files or folders; right-click for Windows actions."))
        splitter.addWidget(folder_panel)

        extension_panel = QWidget(splitter)
        extension_layout = QVBoxLayout(extension_panel)
        extension_layout.setContentsMargins(4, 0, 0, 0)
        extension_layout.setSpacing(6)
        extension_layout.addWidget(StrongBodyLabel("Space by extension"))
        self.extension_table = make_table(
            ["Extension", "Type", "Share", "Size", "Allocated", "Files"], extension_panel
        )
        self.extension_table.verticalHeader().hide()
        self.extension_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.extension_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        for column in range(2, 6):
            self.extension_table.horizontalHeader().setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
        self.extension_table.horizontalHeaderItem(4).setToolTip(
            "Allocated size is estimated from the volume allocation unit for regular files."
        )
        extension_layout.addWidget(self.extension_table, 1)
        extension_layout.addWidget(CaptionLabel("Shows extensions using at least 1% of space; allocation is estimated."))
        splitter.addWidget(extension_panel)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        splitter.setSizes([690, 450])
        layout.addWidget(splitter, 1)

    def _load_drives(self) -> None:
        for storage in QStorageInfo.mountedVolumes():
            if not storage.isValid() or not storage.isReady():
                continue
            root = storage.rootPath()
            if not root:
                continue
            try:
                volume_name = storage.name().strip()
            except AttributeError:
                volume_name = ""
            label = f"{root}  ·  {volume_name}" if volume_name else root
            if label not in self.drive_paths:
                self.drive_paths[label] = Path(root)
        self.drive_combo.addItems(list(self.drive_paths))
        self.drive_combo.setCurrentIndex(-1)

    def _select_drive(self, label: str) -> None:
        if label not in self.drive_paths:
            return
        self.selected_root = self.drive_paths[label]
        self.location_status.setText(f"Selected: {self.selected_root}")

    def _choose_folder(self) -> None:
        selected = QFileDialog.getExistingDirectory(self, "Choose a drive or folder", str(Path.home()))
        if not selected:
            return
        self.selected_root = Path(selected)
        self.drive_combo.blockSignals(True)
        self.drive_combo.setCurrentIndex(-1)
        self.drive_combo.blockSignals(False)
        self.location_status.setText(f"Selected: {self.selected_root}")

    def _start_scan(self) -> None:
        if self.worker and self.worker.isRunning():
            return
        if not self.selected_root or not self.selected_root.is_dir():
            show_error(self, "Choose a location", "Select a drive or choose a folder to scan.")
            return
        self.tree.clear()
        self.root_node = None
        self.extension_stats = {}
        self.delete_folder_button.setEnabled(False)
        self.progress.show()
        self.scan_button.setEnabled(False)
        use_fast_ntfs = self.fast_scan.isChecked() and is_ntfs_path(self.selected_root)
        scan_mode = "fast Windows enumeration" if use_fast_ntfs else "standard scan"
        if self.fast_scan.isChecked() and not use_fast_ntfs:
            scan_mode += " (fast NTFS mode is available only on NTFS volumes)"
        self.location_status.setText(f"Scanning {self.selected_root}…  ·  {scan_mode}")
        self.worker = StorageScanWorker(self.selected_root, use_fast_ntfs)
        self.worker.progress.connect(self._scan_progress)
        self.worker.scan_finished.connect(self._scan_finished)
        self.worker.start()

    def _scan_progress(self, current_path: str, directories: int, files: int) -> None:
        self.location_status.setText(
            f"Scanning {current_path}  ·  {directories:,} folders  ·  {files:,} files"
        )

    def _scan_finished(
        self, root: StorageNode, extensions: dict[str, ExtensionStats], errors: int, directories: int
    ) -> None:
        self.progress.hide()
        self.scan_button.setEnabled(True)
        self.root_node = root
        self.extension_stats = extensions
        self.scan_errors = errors
        self.scan_directories = directories
        self.tree.setUpdatesEnabled(False)
        self.tree.clear()
        root.name = str(root.path)
        root_item = self._make_storage_item(root, root.allocated, is_root=True)
        self.tree.addTopLevelItem(root_item)
        self._set_percent_bar(root_item, 100.0)
        root_item.setExpanded(bool(root.children or root.files))
        self.tree.setUpdatesEnabled(True)
        self._populate_extension_table()
        message = (
            f"Scanned {directories:,} folders and found {root.files:,} files. "
            f"Size: {format_bytes(root.size)}  ·  Allocated: {format_bytes(root.allocated)}."
        )
        if self.worker and self.worker.fast_ntfs:
            message += " Fast NTFS enumeration was used."
        if errors:
            message += f" Skipped {errors:,} inaccessible item(s)."
        self.location_status.setText(message)
        self.parent_window.log_activity(
            "Storage scan",
            f"Scanned {root.path}; {directories:,} folders and {root.files:,} files; "
            f"logical size {format_bytes(root.size)}, allocated {format_bytes(root.allocated)}; "
            f"inaccessible items {errors:,}; mode "
            f"{'fast NTFS enumeration' if self.worker and self.worker.fast_ntfs else 'standard scan'}."
        )

    def _populate_extension_table(self) -> None:
        self.extension_table.setSortingEnabled(False)
        self.extension_table.setRowCount(0)
        denominator = self.root_node.allocated if self.root_node else 0
        total_extensions = sorted(
            (
                (extension, stats)
                for extension, stats in self.extension_stats.items()
                if denominator and stats.allocated * 100 / denominator >= 1
            ),
            key=lambda pair: pair[1].allocated,
            reverse=True,
        )
        self.extension_table.setRowCount(len(total_extensions))
        for row, (extension, stats) in enumerate(total_extensions):
            category = "Other" if extension == "(No Extension)" else file_type(Path(f"sample{extension}"))
            share = stats.allocated * 100 / denominator if denominator else 0.0
            values = [extension, category, f"{share:.1f}%", format_bytes(stats.size),
                      format_bytes(stats.allocated), f"{stats.files:,}"]
            for column, value in enumerate(values):
                if column == 2:
                    share_bar = QProgressBar(self.extension_table)
                    share_bar.setRange(0, 1000)
                    share_bar.setValue(max(0, min(1000, round(share * 10))))
                    share_bar.setFormat(f"{share:.1f}%")
                    share_bar.setTextVisible(True)
                    share_bar.setFixedHeight(18)
                    self.extension_table.setCellWidget(row, column, share_bar)
                    continue
                cell = QTableWidgetItem(value)
                if column >= 3:
                    cell.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self.extension_table.setItem(row, column, cell)

    def _storage_selection_changed(self) -> None:
        can_delete = any(
            isinstance(item.data(0, Qt.ItemDataRole.UserRole), (StorageNode, StorageFile))
            and item.data(0, Qt.ItemDataRole.UserRole) is not self.root_node
            for item in self.tree.selectedItems()
        )
        self.delete_folder_button.setEnabled(
            can_delete and not (self.worker and self.worker.isRunning())
        )

    def _show_storage_context_menu(self, position) -> None:
        item = self.tree.itemAt(position)
        if not item:
            return
        entry = item.data(0, Qt.ItemDataRole.UserRole)
        if not isinstance(entry, (StorageNode, StorageFile)):
            return
        selected_items = self.tree.selectedItems()
        if item not in selected_items:
            self.tree.setCurrentItem(
                item, 0, QItemSelectionModel.SelectionFlag.ClearAndSelect
            )
            selected_items = [item]
        selected_paths = [
            selected.data(0, Qt.ItemDataRole.UserRole).path
            for selected in selected_items
            if isinstance(selected.data(0, Qt.ItemDataRole.UserRole), (StorageNode, StorageFile))
        ]
        # Windows Explorer creates a shell context menu for sibling items. If a
        # tree selection spans directories, show the clicked item's shell menu.
        if len({os.path.normcase(str(path.parent)) for path in selected_paths}) != 1:
            selected_paths = [entry.path]
        point = self.tree.viewport().mapToGlobal(position)
        try:
            invoked = show_windows_shell_context_menu(
                selected_paths, int(self.tree.viewport().winId()), point.x(), point.y()
            )
        except Exception as error:
            show_error(self, "Windows context menu unavailable", str(error))
            return
        if invoked == "delete":
            self._delete_selected_folder()
            return
        if invoked and any(not path.exists() for path in selected_paths):
            self._start_scan()

    def _storage_node_chain(self, node: StorageNode, target: StorageNode) -> list[StorageNode] | None:
        if node is target:
            return [node]
        for child in node.children:
            chain = self._storage_node_chain(child, target)
            if chain:
                return [node, *chain]
        return None

    def _delete_selected_folder(self) -> None:
        if not self.root_node:
            return
        selected = []
        for item in self.tree.selectedItems():
            entry = item.data(0, Qt.ItemDataRole.UserRole)
            if isinstance(entry, StorageNode) and entry is not self.root_node:
                chain = self._storage_node_chain(self.root_node, entry)
                if chain and len(chain) > 1:
                    selected.append((item, entry, chain[:-1]))
            elif isinstance(entry, StorageFile):
                chain = []
                parent_item = item.parent()
                while parent_item:
                    parent = parent_item.data(0, Qt.ItemDataRole.UserRole)
                    if isinstance(parent, StorageNode):
                        chain.append(parent)
                    parent_item = parent_item.parent()
                chain.reverse()
                if chain and chain[0] is self.root_node:
                    selected.append((item, entry, chain))
        if not selected:
            return

        # If both a folder and one of its descendants are selected, process
        # only the folder to avoid trying to delete the same content twice.
        targets = []
        for record in selected:
            _, entry, _ = record
            if any(
                isinstance(other_entry, StorageNode)
                and other_entry is not entry
                and entry.path != other_entry.path
                and entry.path.is_relative_to(other_entry.path)
                for _, other_entry, _ in selected
            ):
                continue
            targets.append(record)

        folders = sum(isinstance(entry, StorageNode) for _, entry, _ in targets)
        files = sum(isinstance(entry, StorageFile) for _, entry, _ in targets)
        names = "\n".join(str(entry.path) for _, entry, _ in targets[:6])
        if len(targets) > 6:
            names += f"\n…and {len(targets) - 6} more"
        if not confirm(
            self,
            "Delete selected items?",
            f"Send {folders} folder(s) and {files} file(s) to the Windows Recycle Bin?\n\n{names}",
        ):
            return

        deleted = []
        errors = []
        for item, entry, ancestors in targets:
            try:
                send_to_recycle_bin(entry.path)
            except (OSError, AttributeError) as error:
                errors.append(f"{entry.path}: {error}")
                continue

            if isinstance(entry, StorageNode):
                size, allocated = entry.size, entry.allocated
                file_count, folder_count = entry.files, entry.folders + 1
                removed_stats = entry.extension_stats
                ancestors[-1].children = [child for child in ancestors[-1].children if child is not entry]
                self.scan_directories = max(1, self.scan_directories - folder_count)
            else:
                size, allocated = entry.size, entry.allocated
                file_count, folder_count = 1, 0
                extension = entry.extension
                removed_stats = {extension: ExtensionStats(entry.size, entry.allocated, 1)}
                ancestors[-1].file_entries = [
                    child for child in ancestors[-1].file_entries if child.path != entry.path
                ]

            for ancestor in ancestors:
                ancestor.size = max(0, ancestor.size - size)
                ancestor.allocated = max(0, ancestor.allocated - allocated)
                ancestor.files = max(0, ancestor.files - file_count)
                ancestor.folders = max(0, ancestor.folders - folder_count)
                self._subtract_extension_stats(ancestor.extension_stats, removed_stats)
            self._subtract_extension_stats(self.extension_stats, removed_stats)
            if item.parent():
                item.parent().removeChild(item)
            deleted.append(entry.path)

        if not deleted:
            show_error(self, "Could not delete selected items", "\n".join(errors[:8]))
            return

        root_item = self.tree.topLevelItem(0)
        if root_item:
            self._refresh_visible_tree(root_item, self.root_node.allocated)
        self._populate_extension_table()
        self._set_scan_status(f"Sent {len(deleted)} item(s) to the Recycle Bin.")
        self.parent_window.log_activity(
            "Storage delete",
            f"Sent {len(deleted)} item(s) to Recycle Bin; failed {len(errors)}. Paths: "
            + "; ".join(str(path) for path in deleted)
        )
        self.delete_folder_button.setEnabled(False)
        if errors:
            show_error(self, "Some items could not be deleted", "\n".join(errors[:8]))

    @staticmethod
    def _subtract_extension_stats(
        aggregate: dict[str, ExtensionStats], removed: dict[str, ExtensionStats]
    ) -> None:
        for extension, removed_stats in removed.items():
            stats = aggregate.get(extension)
            if not stats:
                continue
            stats.size = max(0, stats.size - removed_stats.size)
            stats.allocated = max(0, stats.allocated - removed_stats.allocated)
            stats.files = max(0, stats.files - removed_stats.files)
            if stats.files == 0:
                aggregate.pop(extension, None)

    def _refresh_visible_tree(self, item: QTreeWidgetItem, parent_allocated: int) -> None:
        self._refresh_storage_item(item, parent_allocated)
        node = item.data(0, Qt.ItemDataRole.UserRole)
        child_parent_allocated = node.allocated if isinstance(node, StorageNode) else parent_allocated
        for index in range(item.childCount()):
            self._refresh_visible_tree(item.child(index), child_parent_allocated)

    def _refresh_storage_item(self, item: QTreeWidgetItem, parent_allocated: int) -> None:
        node = item.data(0, Qt.ItemDataRole.UserRole)
        if isinstance(node, StorageFile):
            percent = node.allocated * 100 / parent_allocated if parent_allocated else 0.0
            item.setText(1, format_bytes(node.size))
            item.setText(2, format_bytes(node.allocated))
            item.setText(3, "1")
            item.setText(4, "0")
            item.setText(5, f"{percent:.1f}%")
            return
        if not isinstance(node, StorageNode):
            return
        percent = 100.0 if node is self.root_node else (
            node.allocated * 100 / parent_allocated if parent_allocated else 0.0
        )
        item.setText(1, format_bytes(node.size))
        item.setText(2, format_bytes(node.allocated))
        item.setText(3, f"{node.files:,}")
        item.setText(4, f"{node.folders:,}")
        item.setText(5, f"{percent:.1f}%")
        bar = self.tree.itemWidget(item, 5)
        if isinstance(bar, QProgressBar):
            bar.setValue(max(0, min(1000, round(percent * 10))))
            bar.setFormat(f"{percent:.1f}%")

    def _refresh_visible_child_shares(self, parent_item: QTreeWidgetItem, parent: StorageNode) -> None:
        for index in range(parent_item.childCount()):
            child_item = parent_item.child(index)
            self._refresh_storage_item(child_item, parent.allocated)

    def _set_scan_status(self, prefix: str = "") -> None:
        if not self.root_node:
            return
        message = (
            f"{prefix} {self.scan_directories:,} folders and {self.root_node.files:,} files remain. "
            f"Size: {format_bytes(self.root_node.size)}  ·  Allocated: {format_bytes(self.root_node.allocated)}."
        ).strip()
        if self.worker and self.worker.fast_ntfs:
            message += " Fast NTFS enumeration was used."
        if self.scan_errors:
            message += f" Skipped {self.scan_errors:,} inaccessible item(s)."
        self.location_status.setText(message)

    def _make_storage_item(self, node: StorageNode, parent_allocated: int, is_root: bool = False) -> QTreeWidgetItem:
        percent = 100.0 if is_root else (node.allocated * 100 / parent_allocated if parent_allocated else 0.0)
        item = QTreeWidgetItem([
            node.name,
            format_bytes(node.size),
            format_bytes(node.allocated),
            f"{node.files:,}",
            f"{node.folders:,}",
            f"{percent:.1f}%",
        ])
        item.setIcon(0, self.folder_icon)
        item.setData(0, Qt.ItemDataRole.UserRole, node)
        item.setData(0, Qt.ItemDataRole.UserRole + 1, False)
        item.setToolTip(1, f"Logical size: {node.size:,} bytes")
        item.setToolTip(
            2,
            f"Allocated size estimate: {node.allocated:,} bytes. Regular files use cluster rounding; "
            "compressed and sparse files use filesystem-reported sizes.",
        )
        if node.children or node.files:
            item.addChild(QTreeWidgetItem())
        return item

    def _make_storage_file_item(self, entry: StorageFile, parent_allocated: int) -> QTreeWidgetItem:
        percent = entry.allocated * 100 / parent_allocated if parent_allocated else 0.0
        item = QTreeWidgetItem([
            entry.name,
            format_bytes(entry.size),
            format_bytes(entry.allocated),
            "1",
            "0",
            f"{percent:.1f}%",
        ])
        item.setIcon(0, self.file_icon)
        item.setData(0, Qt.ItemDataRole.UserRole, entry)
        item.setToolTip(1, f"Logical size: {entry.size:,} bytes")
        item.setToolTip(2, f"Allocated size estimate: {entry.allocated:,} bytes")
        return item

    def _set_percent_bar(self, item: QTreeWidgetItem, percent: float) -> None:
        bar = QProgressBar(self.tree)
        bar.setRange(0, 1000)
        bar.setValue(max(0, min(1000, round(percent * 10))))
        bar.setFormat(f"{percent:.1f}%")
        bar.setTextVisible(True)
        bar.setFixedHeight(18)
        self.tree.setItemWidget(item, 5, bar)

    def _expand_storage_item(self, item: QTreeWidgetItem) -> None:
        if item.data(0, Qt.ItemDataRole.UserRole + 1):
            return
        node = item.data(0, Qt.ItemDataRole.UserRole)
        if not isinstance(node, StorageNode):
            return
        item.takeChildren()
        for child in node.children:
            child_item = self._make_storage_item(child, node.allocated)
            item.addChild(child_item)
            percent = child.allocated * 100 / node.allocated if node.allocated else 0.0
            self._set_percent_bar(child_item, percent)
        if not node.files_loaded:
            files: list[StorageFile] = []
            allocation_unit = volume_allocation_unit(node.path)
            try:
                if self.worker and self.worker.fast_ntfs:
                    for name, attributes, size in fast_windows_entries(node.path):
                        if attributes & 0x10 or attributes & 0x400:
                            continue
                        allocated = ((size + allocation_unit - 1) // allocation_unit) * allocation_unit if size else 0
                        extension = os.path.splitext(name)[1].casefold() or "(No Extension)"
                        files.append(StorageFile(node.path / name, name, size, allocated, extension))
                else:
                    with os.scandir(node.path) as entries:
                        for entry in entries:
                            if entry.is_file(follow_symlinks=False):
                                stat = entry.stat(follow_symlinks=False)
                                extension = os.path.splitext(entry.name)[1].casefold() or "(No Extension)"
                                files.append(StorageFile(
                                    Path(entry.path), entry.name, stat.st_size,
                                    allocated_file_size(entry.path, stat, allocation_unit),
                                    extension,
                                ))
            except OSError as error:
                self.location_status.setText(f"Could not list files in {node.path}: {error}")
            node.file_entries = sorted(files, key=lambda entry: entry.allocated, reverse=True)
            node.files_loaded = True
        for entry in node.file_entries:
            item.addChild(self._make_storage_file_item(entry, node.allocated))
        item.setData(0, Qt.ItemDataRole.UserRole + 1, True)


