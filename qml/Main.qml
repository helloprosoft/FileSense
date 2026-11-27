pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls
import QtQuick.Effects
import QtQuick.Layouts
import QtQuick.Dialogs
import QtQuick.Shapes

ApplicationWindow {
    id: window
    width: 1440
    height: 900
    minimumWidth: 1060
    minimumHeight: 700
    visible: true
    title: "FileSense"
    property bool lightAppearance: fileSense.lightAppearance
    color: lightAppearance ? "#f3f1ed" : "#090a0b"

    property color panel: lightAppearance ? "#fbfaf8" : "#111315"
    property color panelRaised: lightAppearance ? "#f1efeb" : "#191b1d"
    property color border: lightAppearance ? "#dedbd5" : "#25282a"
    property color textMain: lightAppearance ? "#1c2225" : "#f2f5f6"
    property color textMuted: lightAppearance ? "#5f696c" : "#a6b0b4"
    property color accent: "#4c8ab0"
    property real buttonRadius: 6
    property string activePage: "Home"
    property bool sidebarCollapsed: true
    property string startupSearchText: ""
    property bool startupAdvancedView: false
    property bool searchFiltersExpanded: true
    property int storageActiveTab: 0
    property string storageTreemapPath: ""
    property int storageTreemapDepthLimit: 0
    property int storageTreemapMetric: 0
    property int storageTreemapSort: 0
    property real sidebarWidth: 72
    property real sidebarIconCellWidth: 56
    property bool modalDialogVisible: organizeConfirm.visible || ruleConfirm.visible || ruleDestinationDialog.visible || storagePathDialog.visible || cleanDialog.visible || cleanupResultsDialog.visible || activationDialog.visible || activationThanksDialog.visible || startupActionDialog.visible || startupConfirmationDialog.visible || duplicateConfirm.visible
    property bool activationThankYouShown: false
    property var resultSorts: ({})
    property int resultSortRevision: 0
    function requestResultSort(scope, key, kind) {
        var old = resultSorts[scope] || {};
        var nextSort = { key: key, kind: kind, descending: old.key === key ? !old.descending : false };
        var updated = {};
        for (var name in resultSorts) updated[name] = resultSorts[name];
        updated[scope] = nextSort;
        resultSorts = updated;
        resultSortRevision++;
        if (scope === "duplicates") rebuildDuplicateResultRows();
    }
    function compareResultValues(left, right, key, kind) {
        var a = left === undefined || left === null ? "" : left;
        var b = right === undefined || right === null ? "" : right;
        if (kind === "number" || kind === "size" || typeof a === "number" || typeof b === "number") {
            function numberValue(value) {
                if (typeof value === "number") return value;
                var match = String(value).replace(/,/g, "").match(/-?[0-9]+(?:[.][0-9]+)?[ \t]*(B|KB|MB|GB|TB)?/i);
                if (!match) return -1;
                var amount = parseFloat(match[0]);
                var unit = (match[1] || "").toUpperCase();
                var scale = { B: 1, KB: 1024, MB: 1048576, GB: 1073741824, TB: 1099511627776 };
                return amount * (scale[unit] || 1);
            }
            return numberValue(a) - numberValue(b);
        }
        if (kind === "date") {
            var dateA = Date.parse(a), dateB = Date.parse(b);
            if (!isNaN(dateA) && !isNaN(dateB)) return dateA - dateB;
        }
        var textA = String(a).toLowerCase(), textB = String(b).toLowerCase();
        return textA < textB ? -1 : (textA > textB ? 1 : 0);
    }
    function sortedResultRows(source, scope) {
        var revision = resultSortRevision;
        var rows = source ? source.slice(0) : [];
        var sort = resultSorts[scope];
        if (!sort || !sort.key) return rows;
        rows.sort(function(a, b) {
            var comparison = compareResultValues(a[sort.key], b[sort.key], sort.key, sort.kind);
            return sort.descending ? -comparison : comparison;
        });
        return rows;
    }
    function sortedJunkCategories() {
        var rows = fileSense.categories ? fileSense.categories.slice(0) : [];
        var groupOrder = ["Recommended items · Application items", "Recommended items · System items",
                          "Other application items", "Other system items"];
        var sort = resultSorts["junkCategories"];
        rows.sort(function(a, b) {
            var groupA = groupOrder.indexOf(a.group);
            var groupB = groupOrder.indexOf(b.group);
            if (groupA < 0) groupA = groupOrder.length;
            if (groupB < 0) groupB = groupOrder.length;
            if (groupA !== groupB) return groupA - groupB;
            if (sort && sort.key) {
                var comparison = compareResultValues(a[sort.key], b[sort.key], sort.key, sort.kind);
                if (comparison !== 0) return sort.descending ? -comparison : comparison;
            }
            return compareResultValues(a.name, b.name, "name", "text");
        });
        for (var i = 0; i < rows.length; ++i) {
            rows[i] = Object.assign({}, rows[i], {
                startsGroup: i === 0 || rows[i].group !== rows[i - 1].group
            });
        }
        return rows;
    }
    function junkGroupCheckState(group) {
        var categories = fileSense.categories || [];
        var total = 0, selected = 0;
        for (var i = 0; i < categories.length; ++i) {
            if (categories[i].group !== group) continue;
            total += Number(categories[i].itemCount || 0);
            selected += Number(categories[i].selectedCount || 0);
        }
        if (!total || !selected) return Qt.Unchecked;
        return selected >= total ? Qt.Checked : Qt.PartiallyChecked;
    }
    function updateJunkSelection(action) {
        var scrollPosition = junkCategoryList.contentY;
        action();
        Qt.callLater(function () {
            var maxScroll = Math.max(0, junkCategoryList.contentHeight - junkCategoryList.height);
            junkCategoryList.contentY = Math.max(0, Math.min(scrollPosition, maxScroll));
        });
    }
    function sortedStorageRows(source) {
        var revision = resultSortRevision;
        var rows = source ? source.slice(0) : [];
        var sort = resultSorts.storageFolders;
        if (!sort || !sort.key || rows.length < 2) return rows;
        var roots = [], stack = [];
        for (var i = 0; i < rows.length; ++i) {
            var node = { row: rows[i], children: [] };
            var depth = Number(rows[i].depth || 0);
            while (stack.length > depth) stack.pop();
            if (depth === 0) roots.push(node);
            else if (stack[depth - 1]) stack[depth - 1].children.push(node);
            stack[depth] = node;
        }
        function orderNodes(nodes) {
            nodes.sort(function(a, b) {
                var result = compareResultValues(a.row[sort.key], b.row[sort.key], sort.key, sort.kind);
                return sort.descending ? -result : result;
            });
            for (var n = 0; n < nodes.length; ++n) orderNodes(nodes[n].children);
        }
        orderNodes(roots);
        var flattened = [];
        function flatten(nodes) {
            for (var j = 0; j < nodes.length; ++j) {
                flattened.push(nodes[j].row);
                flatten(nodes[j].children);
            }
        }
        flatten(roots);
        return flattened;
    }
    function normalizedStoragePath(path) {
        return String(path || "").replace(/\\/g, "/").replace(/\/+$/g, "").toLowerCase();
    }
    function storageParentPath(path) {
        var value = String(path || "").replace(/\\/g, "/");
        if (/^[a-z]:\/?$/i.test(value) || value === "/") return "";
        value = value.replace(/\/+$/g, "");
        var slash = value.lastIndexOf("/");
        if (slash < 0) return "";
        if (slash === 2 && value.length > 1 && value[1] === ":") return value.slice(0, 3);
        return value.slice(0, slash);
    }
    function storageTreemapBreadcrumbs() {
        var rootPath = String(fileSense.storageRootPath || "");
        if (!rootPath) return [];
        var currentPath = storageTreemapPath || rootPath;
        var rootNorm = normalizedStoragePath(rootPath);
        var currentNorm = normalizedStoragePath(currentPath);
        if (currentNorm !== rootNorm && currentNorm.indexOf(rootNorm + "/") !== 0)
            currentPath = rootPath;
        var normalizedCurrent = normalizedStoragePath(currentPath);
        var rootName = rootPath.replace(/[\\/]+$/g, "").split(/[\\/]/).pop() || rootPath;
        var chain = [{ name: rootName, path: rootPath }];
        if (normalizedCurrent !== rootNorm) {
            var relative = currentPath.replace(/\\/g, "/").slice(rootPath.replace(/\\/g, "/").replace(/\/+$/g, "").length);
            var parts = relative.split("/").filter(function(part) { return !!part; });
            var builtPath = rootPath.replace(/[\\/]+$/g, "");
            for (var i = 0; i < parts.length; ++i) {
                builtPath += "/" + parts[i];
                chain.push({ name: parts[i], path: builtPath });
            }
        }
        return chain;
    }
    function storageTreemapMetricValue(row) {
        if (storageTreemapMetric === 1) return Math.max(0, Number(row.fileCount || row.files || (row.kind === "file" ? 1 : 0)));
        if (storageTreemapMetric === 2) return Math.max(0, Number(row.allocatedBytes || 0));
        return Math.max(0, Number(row.sizeBytes || 0));
    }
    function storageTreemapMetricLabel(row) {
        if (storageTreemapMetric === 1) {
            var count = Number(row.fileCount || row.files || (row.kind === "file" ? 1 : 0));
            return count.toLocaleString() + (count === 1 ? " file" : " files");
        }
        return storageTreemapMetric === 2 ? (row.allocated || "0 B") : (row.size || "0 B");
    }
    function enterStorageTreemap(row) {
        if (!row || row.kind !== "folder" || !row.path || !row.canExpand) return;
        var crumbs = storageTreemapBreadcrumbs();
        var currentDepth = Math.max(0, crumbs.length - 1);
        if (storageTreemapDepthLimit > 0 && currentDepth >= storageTreemapDepthLimit) return;
        storageTreemapPath = row.path;
        fileSense.storageTreemapChildren(row.path, storageTreemapMetric, storageTreemapSort);
    }
    function setStorageTreemapDepthLimit(limit) {
        storageTreemapDepthLimit = limit;
        var crumbs = storageTreemapBreadcrumbs();
        if (limit > 0 && crumbs.length > limit + 1)
            storageTreemapPath = crumbs[limit].path;
    }
    function storageTreemapTiles() {
        // Track completed asynchronous folder listings without coupling this view
        // to the folder breakdown table's flattened rows.
        var dataRevision = fileSense.storageDataRevision;
        var rootPath = String(fileSense.storageRootPath || "");
        if (!rootPath) return [];
        var currentPath = storageTreemapPath || rootPath;
        var rows = fileSense.storageTreemapChildren(currentPath, storageTreemapMetric, storageTreemapSort) || [];
        var items = [];
        for (var j = 0; j < rows.length; ++j) {
            var row = rows[j];
            var value = storageTreemapMetricValue(row);
            var fileCount = Number(row.fileCount || row.files || (row.kind === "file" ? 1 : 0));
            items.push({
                name: row.name, path: row.path, kind: row.kind,
                size: row.size || "0 B", allocated: row.allocated || "0 B",
                fileCount: fileCount, metricText: storageTreemapMetricLabel(row),
                value: value, row: row
            });
        }
        if (!items.length) return [];
        items.sort(function(a, b) {
            if (storageTreemapSort === 2) {
                var nameA = String(a.name).toLowerCase(), nameB = String(b.name).toLowerCase();
                return nameA < nameB ? -1 : (nameA > nameB ? 1 : 0);
            }
            return storageTreemapSort === 1 ? a.value - b.value : b.value - a.value;
        });
        var total = 0;
        for (var k = 0; k < items.length; ++k) total += items[k].value;
        if (total <= 0) {
            total = items.length;
            for (var z = 0; z < items.length; ++z) items[z].value = 1;
        }
        for (var a = 0; a < items.length; ++a) items[a].area = items[a].value / total;

        var tiles = [];
        function addTile(item, x, y, w, h) {
            tiles.push({ name: item.name, path: item.path, kind: item.kind,
                         size: item.size, allocated: item.allocated, fileCount: item.fileCount,
                         metricText: item.metricText, value: item.value,
                         row: item.row, x: x, y: y, w: w, h: h });
        }
        function worst(row, side) {
            if (!row.length) return Number.POSITIVE_INFINITY;
            var sum = 0, minArea = Number.POSITIVE_INFINITY, maxArea = 0;
            for (var n = 0; n < row.length; ++n) {
                sum += row[n].area;
                minArea = Math.min(minArea, row[n].area);
                maxArea = Math.max(maxArea, row[n].area);
            }
            if (minArea <= 0 || sum <= 0 || side <= 0) return Number.POSITIVE_INFINITY;
            var side2 = side * side, sum2 = sum * sum;
            return Math.max((side2 * maxArea) / sum2, sum2 / (side2 * minArea));
        }
        function placeRow(row, rect, horizontal) {
            var area = 0;
            for (var n = 0; n < row.length; ++n) area += row[n].area;
            if (horizontal) {
                var stripHeight = area / rect.w;
                var xx = rect.x;
                for (var h = 0; h < row.length; ++h) {
                    var tileWidth = row[h].area / stripHeight;
                    addTile(row[h], xx, rect.y, tileWidth, stripHeight);
                    xx += tileWidth;
                }
                return { x: rect.x, y: rect.y + stripHeight, w: rect.w, h: Math.max(0, rect.h - stripHeight) };
            }
            var stripWidth = area / rect.h;
            var yy = rect.y;
            for (var v = 0; v < row.length; ++v) {
                var tileHeight = row[v].area / stripWidth;
                addTile(row[v], rect.x, yy, stripWidth, tileHeight);
                yy += tileHeight;
            }
            return { x: rect.x + stripWidth, y: rect.y, w: Math.max(0, rect.w - stripWidth), h: rect.h };
        }
        function squarify(remaining, rect) {
            if (!remaining.length || rect.w <= 0 || rect.h <= 0) return;
            if (remaining.length === 1) {
                addTile(remaining[0], rect.x, rect.y, rect.w, rect.h);
                return;
            }
            var rest = remaining.slice(0), box = rect;
            while (rest.length) {
                var horizontal = box.w >= box.h;
                var side = Math.min(box.w, box.h);
                var row = [rest.shift()];
                while (rest.length && worst(row.concat([rest[0]]), side) <= worst(row, side)) row.push(rest.shift());
                box = placeRow(row, box, horizontal);
                if (rest.length) squarify(rest, box);
                return;
            }
        }
        squarify(items, { x: 0, y: 0, w: 1, h: 1 });
        return tiles;
    }
    function sortedHeader(scope, key, kind) { requestResultSort(scope, key, kind); }
    function requestJunkSort(itemKey, categoryKey, itemKind, categoryKind) {
        requestResultSort("junkItems", itemKey, itemKind);
        fileSense.sortJunkResults(itemKey, resultSorts.junkItems.descending);
        if (categoryKey) requestResultSort("junkCategories", categoryKey, categoryKind || "text");
    }
    function iconForPage(pageName) {
        for (var i = 0; i < pages.length; ++i) {
            if (pages[i].name === pageName)
                return pages[i].icon;
        }
        return "";
    }
    function filterStartupRows(source) {
        var query = startupSearchText.trim().toLowerCase();
        var rows = source ? source.slice(0) : [];
        if (!query) return rows;
        return rows.filter(function(row) {
            return [row.name, row.publisher, row.status, row.impact, row.duplicate, row.executable, row.location]
                .join(" ").toLowerCase().indexOf(query) >= 0;
        });
    }
    function startupFilterCount() {
        var cats = fileSense.categories || [];
        for (var i = 0; i < cats.length; ++i)
            if (cats[i].key === fileSense.startupFilter) return Number(cats[i].detail || 0);
        return 0;
    }
    function startupCategoryTitle() {
        return fileSense.startupFilter === "Startup apps" ? "Startup Programs" : fileSense.startupFilter;
    }
    function requestStartupAction(row) {
        if (!row || !row.entryId) return;
        fileSense.selectStartup(row.entryId);
        if (row.category === "Services") {
            fileSense.serviceAction(row.entryId, row.status === "Disabled");
        } else if (row.enabledAction || row.disabledAction) {
            startupActionDialog.enable = row.status === "Disabled";
            startupActionDialog.open();
        }
    }
    function junkCategoryIconIndex(key) {
        var icons = {
            user_temp: 0, windows_temp: 1, recycle_bin: 2,
            thumbnail_cache: 3, directx_cache: 4, wer_reports: 5,
            application_cache: 6, browser_cache: 7, logs: 8,
            crash_dumps: 9, update_cleanup: 10, delivery_cache: 11,
            empty_folders: 0, chrome_cache: 7, edge_cache: 7, firefox_cache: 7,
            nvidia_cache: 6, python_pip_cache: 6, windows_minidumps: 9, prefetch: 1
        };
        return icons[key] !== undefined ? icons[key] : 8;
    }
    function junkCategoryIconCropY(key) {
        var cropPositions = [7, 96, 188, 279, 366, 456, 544, 627, 711, 793, 878, 961];
        return cropPositions[junkCategoryIconIndex(key)] || 7;
    }
    Behavior on sidebarWidth {
        NumberAnimation {
            duration: 320
            easing.type: Easing.InOutCubic
        }
    }
    Behavior on sidebarIconCellWidth {
        NumberAnimation {
            duration: 260
            easing.type: Easing.InOutCubic
        }
    }
    property string organizerTab: "Quick Organize"
    property string duplicateMode: "Find duplicates"
    property var duplicateExpandedGroups: ({})
    property int selectedExcludedFolderIndex: -1
    function excludedFolderPaths() {
        var result = [];
        for (var i = 0; i < quickExcludedFolders.count; ++i)
            result.push(quickExcludedFolders.get(i).path);
        return result;
    }
    function collectRuleConditions() {
        var result = [];
        for (var i = 0; i < ruleConditions.count; ++i) {
            var condition = ruleConditions.get(i);
            result.push({
                logic: condition.logic,
                field: condition.field,
                operator: condition.operator,
                typeValue: condition.typeValue,
                value: condition.value,
                unit: condition.unit,
                dateKind: condition.dateKind,
                startDate: condition.startDate,
                endDate: condition.endDate,
                period: condition.period,
                periodUnit: condition.periodUnit
            });
        }
        return result;
    }
    function validateRuleFolders() {
        var roots = ruleMonitorPaths.text.split(";").map(function (path) { return path.trim(); }).filter(function (path) { return path.length > 0; });
        var missingSource = roots.length === 0;
        var missingDestination = ruleAction.currentText !== "Delete file" && !ruleDestination.text.trim();
        if (missingSource || missingDestination) {
            if (missingSource && missingDestination)
                ruleDestinationDialog.messageText = "Add at least one monitored source folder and choose a destination folder before previewing or running this rule.";
            else if (missingSource)
                ruleDestinationDialog.messageText = "Add at least one monitored source folder before previewing or running this rule.";
            else
                ruleDestinationDialog.messageText = "Choose a destination folder before previewing or running a Move or Copy rule.";
            ruleDestinationDialog.open();
            return false;
        }
        return true;
    }
    function openRuleDatePicker(rowIndex, propertyName, currentValue, anchorItem) {
        ruleDatePicker.conditionIndex = rowIndex;
        ruleDatePicker.dateProperty = propertyName;
        ruleDatePicker.targetField = "";
        var parsedDate = new Date();
        if (currentValue) {
            var dateParts = currentValue.split("-");
            if (dateParts.length === 3 && dateParts[0].length === 2)
                parsedDate = new Date(Number(dateParts[2]), Number(dateParts[0]) - 1, Number(dateParts[1]));
            else
                parsedDate = new Date(currentValue + "T00:00:00");
        }
        ruleDatePicker.selectedDate = isNaN(parsedDate.getTime()) ? new Date() : parsedDate;
        ruleDatePicker.displayedMonth = new Date(ruleDatePicker.selectedDate.getFullYear(), ruleDatePicker.selectedDate.getMonth(), 1);
        var anchorPosition = anchorItem.mapToItem(ruleDatePicker.parent, anchorItem.width, anchorItem.height + 4);
        ruleDatePicker.x = Math.max(8, Math.min(anchorPosition.x - ruleDatePicker.width, ruleDatePicker.parent.width - ruleDatePicker.width - 8));
        ruleDatePicker.y = anchorPosition.y + ruleDatePicker.height <= ruleDatePicker.parent.height - 8 ? anchorPosition.y : Math.max(8, anchorPosition.y - anchorItem.height - ruleDatePicker.height - 8);
        ruleDatePicker.open();
    }
    function setSearchDateField(fieldName, dateText) {
        if (fieldName === "createdFrom") createdFrom.text = dateText;
        else if (fieldName === "createdTo") createdTo.text = dateText;
        else if (fieldName === "modifiedFrom") modifiedFrom.text = dateText;
        else if (fieldName === "modifiedTo") modifiedTo.text = dateText;
    }
    function searchExcludedFolderPaths() {
        var paths = [];
        for (var i = 0; i < searchExcludedFolders.count; ++i)
            paths.push(searchExcludedFolders.get(i).path);
        return paths;
    }
    function addSearchExcludedFolder(path) {
        for (var i = 0; i < searchExcludedFolders.count; ++i) {
            if (searchExcludedFolders.get(i).path.toLowerCase() === path.toLowerCase())
                return;
        }
        searchExcludedFolders.append({ path: path });
    }
    function openSearchDatePicker(fieldName, currentValue, anchorItem) {
        ruleDatePicker.conditionIndex = -1;
        ruleDatePicker.targetField = fieldName;
        var parsedDate = new Date();
        if (currentValue) {
            var dateParts = currentValue.split("-");
            if (dateParts.length === 3 && dateParts[0].length === 2)
                parsedDate = new Date(Number(dateParts[2]), Number(dateParts[0]) - 1, Number(dateParts[1]));
        }
        ruleDatePicker.selectedDate = isNaN(parsedDate.getTime()) ? new Date() : parsedDate;
        ruleDatePicker.displayedMonth = new Date(ruleDatePicker.selectedDate.getFullYear(), ruleDatePicker.selectedDate.getMonth(), 1);
        var anchorPosition = anchorItem.mapToItem(ruleDatePicker.parent, anchorItem.width, anchorItem.height + 4);
        ruleDatePicker.x = Math.max(8, Math.min(anchorPosition.x - ruleDatePicker.width, ruleDatePicker.parent.width - ruleDatePicker.width - 8));
        ruleDatePicker.y = anchorPosition.y + ruleDatePicker.height <= ruleDatePicker.parent.height - 8 ? anchorPosition.y : Math.max(8, anchorPosition.y - anchorItem.height - ruleDatePicker.height - 8);
        ruleDatePicker.open();
    }
    property var pages: [
        {
            name: "Home",
            icon: "\uE80F"
        },
        {
            name: "File Organizer",
            icon: "\uEC50"
        },
        {
            name: "Storage Analyzer",
            icon: "\uEB05"
        },
        {
            name: "File Search & Finder",
            icon: "\uE721"
        },
        {
            name: "Duplicate Finder",
            icon: "\uE8C8"
        },
        {
            name: "Junk Cleaner",
            icon: "\uE74D"
        },
        {
            name: "Startup Manager",
            icon: "\uE7E8"
        },
        {
            name: "Recent Activity",
            icon: "\uE81C"
        },
        {
            name: "Read Me",
            icon: "\uE736"
        },
        {
            name: "About",
            icon: "\uE946"
        }
    ]

    ListModel {
        id: ruleConditions
        ListElement {
            logic: "AND"
            field: "File Type"
            operator: "Is"
            typeValue: "Images"
            value: ""
            unit: "MB"
            dateKind: "Date modified"
            startDate: ""
            endDate: ""
            period: "7"
            periodUnit: "Days"
        }
    }
    ListModel {
        id: quickExcludedFolders
    }
    ListModel {
        id: searchExcludedFolders
    }
    ListModel {
        id: duplicateExcludedFolders
    }
    ListModel {
        id: duplicateConditions
        ListElement { logic: "AND"; field: "File Type"; operator: "Is"; typeValue: "Images"; value: "" }
    }
    ListModel {
        id: duplicateResultRows
    }
    function collectDuplicateConditions() {
        var result = [];
        for (var i = 0; i < duplicateConditions.count; ++i) {
            var condition = duplicateConditions.get(i);
            result.push({
                logic: condition.logic,
                field: condition.field,
                operator: condition.operator,
                typeValue: condition.typeValue,
                value: condition.value
            });
        }
        return result;
    }
    function setDuplicateCondition(index, role, value) {
        if (index >= 0 && index < duplicateConditions.count)
            duplicateConditions.setProperty(index, role, value);
    }
    function duplicateExcludedFolderPaths() {
        var result = [];
        for (var i = 0; i < duplicateExcludedFolders.count; ++i)
            result.push(duplicateExcludedFolders.get(i).path);
        return result;
    }
    function duplicateDeleteSelectionCount() {
        var count = 0;
        for (var i = 0; i < fileSense.duplicateRows.length; ++i) {
            if (fileSense.duplicateRows[i].duplicateGroup && fileSense.duplicateRows[i].deleteSelected)
                count++;
        }
        return count;
    }
    function rebuildDuplicateResultRows() {
        duplicateResultRows.clear();
        var grouped = {};
        var order = [];
        var scope = duplicateMode === "Build a rule" ? "duplicateRule" : "duplicateFind";
        var rows = sortedResultRows(fileSense.duplicateRows || [], scope);
        for (var i = 0; i < rows.length; ++i) {
            var row = rows[i];
            var key = String(row.duplicateGroup || "");
            if (!key)
                continue;
            if (!grouped[key]) {
                grouped[key] = [];
                order.push(key);
            }
            grouped[key].push(row);
        }
        for (var g = 0; g < order.length; ++g) {
            var groupKey = order[g];
            var entries = grouped[groupKey];
            var expansionKey = scope + "|" + groupKey;
            var expanded = duplicateExpandedGroups[expansionKey] !== false;
            duplicateResultRows.append({
                rowKind: "group", groupKey: groupKey, expanded: expanded,
                name: (entries[0].name || "") + " (" + entries.length + " entries)",
                fileType: "Group", sizeText: "—", deleteSelected: false,
                sizeComparison: entries.length > 0 ? (entries[0].sizeComparison || "—") : "—",
                path: ""
            });
            if (!expanded)
                continue;
            for (var e = 0; e < entries.length; ++e) {
                var entry = entries[e];
                duplicateResultRows.append({
                    rowKind: "entry", groupKey: groupKey, expanded: false,
                    name: entry.name || "", fileType: entry.fileType || "File",
                    sizeText: entry.sizeText || "—", sizeComparison: "—",
                    path: entry.path || "", deleteSelected: entry.deleteSelected === true
                });
            }
        }
    }
    function toggleDuplicateGroup(groupKey) {
        var scope = duplicateMode === "Build a rule" ? "duplicateRule" : "duplicateFind";
        var expansionKey = scope + "|" + groupKey;
        duplicateExpandedGroups[expansionKey] = duplicateExpandedGroups[expansionKey] === false;
        rebuildDuplicateResultRows();
    }
    function selectDuplicateMode(mode) {
        duplicateMode = mode;
        fileSense.setDuplicateMode(mode === "Build a rule" ? "rule" : "find");
        rebuildDuplicateResultRows();
    }
    function addDuplicateExcludedFolder(path) {
        for (var i = 0; i < duplicateExcludedFolders.count; ++i) {
            if (duplicateExcludedFolders.get(i).path.toLowerCase() === path.toLowerCase())
                return;
        }
        duplicateExcludedFolders.append({ path: path });
    }

    Connections {
        target: fileSense
        function onChanged() { window.rebuildDuplicateResultRows(); }
    }
    function selectedSearchCategories() {
        var result = [];
        for (var i = 0; i < searchCategoryRepeater.count; ++i) {
            var item = searchCategoryRepeater.itemAt(i);
            if (item && item.checked) result.push(item.text);
        }
        return result.join(",");
    }
    function appendSearchLocation(path) {
        var paths = searchRoots.text ? searchRoots.text.split(";") : [];
        for (var i = 0; i < paths.length; ++i)
            if (paths[i].trim().toLowerCase() === path.toLowerCase()) return;
        searchRoots.text = searchRoots.text ? searchRoots.text + ";" + path : path;
    }

    Component {
        id: actionButton
        FocusScope {
            id: control
            property string text: ""
            property string iconText: ""
            property string iconFontFamily: "Segoe MDL2 Assets"
            property bool pressed: false
            property bool hovered: false
            signal clicked
            implicitHeight: 30
            implicitWidth: label.implicitWidth + 32 + (iconText ? 22 : 0)
            activeFocusOnTab: true
            Rectangle {
                id: buttonSurface
                anchors.fill: parent
                radius: window.buttonRadius
                color: !control.enabled ? "#45494c" : control.pressed ? Qt.darker(window.accent, 1.25) : control.hovered ? Qt.darker(window.accent, 1.12) : window.accent
                border.color: !control.enabled ? "#45494c" : (control.activeFocus ? Qt.lighter(window.accent, 1.35) : Qt.lighter(window.accent, 1.15))
                border.width: control.activeFocus ? 2 : 1
                Behavior on color {
                    ColorAnimation {
                        duration: 150
                    }
                }
                Behavior on border.color {
                    ColorAnimation {
                        duration: 160
                    }
                }
                Behavior on border.width {
                    NumberAnimation {
                        duration: 160
                        easing.type: Easing.OutCubic
                    }
                }
            }
            Row {
                anchors.centerIn: parent
                spacing: 8
                Item {
                    visible: control.iconText !== ""
                    width: 16
                    height: 18
                    Text {
                        anchors.centerIn: parent
                        anchors.verticalCenterOffset: 1
                        text: control.iconText
                        color: control.enabled ? "#102321" : "#8b9295"
                        font.family: control.iconFontFamily
                        font.pixelSize: 14
                        font.bold: true
                    }
                }
                Text {
                    id: label
                    text: control.text
                    color: control.enabled ? "#102321" : "#8b9295"
                    font.pixelSize: 14
                    font.bold: true
                    verticalAlignment: Text.AlignVCenter
                    elide: Text.ElideRight
                }
            }
            Keys.onReturnPressed: control.clicked()
            Keys.onEnterPressed: control.clicked()
            Keys.onSpacePressed: control.clicked()
            MouseArea {
                anchors.fill: parent
                enabled: control.enabled
                hoverEnabled: true
                cursorShape: control.enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
                onEntered: control.hovered = true
                onExited: control.hovered = false
                onPressed: {
                    control.pressed = true;
                    control.forceActiveFocus();
                }
                onReleased: control.pressed = false
                onCanceled: control.pressed = false
                onClicked: control.clicked()
            }
        }
    }

    component AppButton: Button {
        font.bold: true
    }

    component StartupActionButton: AppButton {
        id: startupActionButton
        property string iconText: ""
        property bool primaryAction: false
        implicitHeight: 36
        leftPadding: 13
        rightPadding: 15
        spacing: 8
        font.pixelSize: 14
        contentItem: Row {
            anchors.centerIn: parent
            height: parent.height
            spacing: 8
            Text {
                text: startupActionButton.iconText
                height: parent.height
                font.family: "Segoe MDL2 Assets"
                color: startupActionButton.enabled
                       ? (startupActionButton.primaryAction ? "#102321" : window.textMain)
                       : window.textMuted
                font.pixelSize: 14
                font.bold: true
                verticalAlignment: Text.AlignVCenter
            }
            Text {
                text: startupActionButton.text
                height: parent.height
                color: startupActionButton.enabled
                       ? (startupActionButton.primaryAction ? "#102321" : window.textMain)
                       : window.textMuted
                font.pixelSize: 14
                font.bold: true
                verticalAlignment: Text.AlignVCenter
            }
        }
        background: Rectangle {
            radius: window.buttonRadius
            color: startupActionButton.enabled
                   ? (startupActionButton.primaryAction
                      ? (startupActionButton.down ? Qt.darker(window.accent, 1.2) : window.accent)
                      : (startupActionButton.down ? window.panel : window.panelRaised))
                   : (window.lightAppearance ? "#e9e7e2" : "#222527")
            border.color: startupActionButton.activeFocus
                          ? Qt.lighter(window.accent, 1.35) : window.border
            border.width: startupActionButton.activeFocus ? 2 : 1
        }
    }

    Component {
        id: coffeeButton
        AppButton {
            id: control
            implicitHeight: 30
            leftPadding: 14
            rightPadding: 14
            font.pixelSize: 13
            contentItem: Text {
                text: control.text
                color: "#241710"
                font.pixelSize: control.font.pixelSize
                font.bold: true
                verticalAlignment: Text.AlignVCenter
                horizontalAlignment: Text.AlignHCenter
            }
            background: Rectangle {
                radius: window.buttonRadius
                color: control.down ? "#d96b38" : "#f28a55"
                border.color: "#e87543"
                border.width: 1
            }
        }
    }

    component AnimatedProgressBar: Item {
        id: animatedProgressBar
        property bool running: false
        property color trackColor: window.panelRaised
        property color progressColor: window.accent
        property real segmentFraction: 0.32
        property int animationDuration: 1050
        implicitHeight: 6
        Rectangle {
            anchors.fill: parent
            radius: height / 2
            color: animatedProgressBar.trackColor
            clip: true
            Rectangle {
                id: animatedProgressSegment
                width: parent.width * animatedProgressBar.segmentFraction
                height: parent.height
                radius: height / 2
                color: animatedProgressBar.progressColor
                SequentialAnimation on x {
                    running: animatedProgressBar.running && animatedProgressBar.width > 0
                    loops: Animation.Infinite
                    NumberAnimation {
                        from: -animatedProgressSegment.width
                        to: animatedProgressBar.width
                        duration: animatedProgressBar.animationDuration
                        easing.type: Easing.InOutCubic
                    }
                    PauseAnimation { duration: 120 }
                }
            }
        }
    }

    component DialogActionButton: FocusScope {
        id: dialogButton
        property string text: ""
        property bool primary: true
        property bool coffee: false
        property bool hovered: false
        signal clicked
        implicitHeight: 34
        implicitWidth: dialogButtonLabel.implicitWidth + 30
        activeFocusOnTab: true
        Rectangle {
            anchors.fill: parent
            radius: window.buttonRadius
            color: dialogButton.coffee ? (dialogButton.hovered ? "#FFA06F" : "#F28A55") : dialogButton.primary ? (dialogButton.hovered ? Qt.darker(window.accent, 1.12) : window.accent) : (dialogButton.hovered ? window.panel : window.panelRaised)
            border.color: dialogButton.coffee ? "#E87543" : dialogButton.primary ? Qt.lighter(window.accent, 1.15) : window.border
            Text {
                id: dialogButtonLabel
                anchors.fill: parent
                anchors.leftMargin: 15
                anchors.rightMargin: 15
                text: dialogButton.text
                color: dialogButton.coffee ? "#241710" : dialogButton.primary ? "#102321" : window.textMain
                font.pixelSize: 13
                font.bold: true
                horizontalAlignment: Text.AlignHCenter
                verticalAlignment: Text.AlignVCenter
            }
        }
        MouseArea {
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onEntered: dialogButton.hovered = true
            onExited: dialogButton.hovered = false
            onClicked: dialogButton.clicked()
        }
        Keys.onReturnPressed: dialogButton.clicked()
        Keys.onEnterPressed: dialogButton.clicked()
        Keys.onSpacePressed: dialogButton.clicked()
    }

    component DialogMessage: RowLayout {
        id: dialogMessage
        property string message: ""
        property string iconType: "question"
        spacing: 14
        Item {
            Layout.preferredWidth: 40
            Layout.preferredHeight: 40
            Rectangle {
                anchors.fill: parent
                radius: width / 2
                color: dialogMessage.iconType === "error" ? "#e94b35" : dialogMessage.iconType === "warning" ? "#e99435" : dialogMessage.iconType === "success" ? "#25a77a" : dialogMessage.iconType === "info" ? "#1788d4" : "#3478c8"
                Text {
                    anchors.fill: parent
                    text: dialogMessage.iconType === "error" ? "×" : dialogMessage.iconType === "success" ? "✓" : dialogMessage.iconType === "warning" ? "!" : dialogMessage.iconType === "info" ? "i" : "?"
                    color: "white"
                    font.pixelSize: dialogMessage.iconType === "error" ? 30 : 23
                    font.bold: true
                    horizontalAlignment: Text.AlignHCenter
                    verticalAlignment: Text.AlignVCenter
                }
            }
        }
        Text {
            text: dialogMessage.message
            color: window.textMain
            font.pixelSize: 14
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
            verticalAlignment: Text.AlignVCenter
        }
    }

    component ThemedDialog: Dialog {
        id: themedDialog
        property string acceptText: "Continue"
        property bool showCancel: true
        property bool closeOnly: false
        width: 500
        padding: 18
        modal: true
        anchors.centerIn: Overlay.overlay
        background: Rectangle {
            color: window.panel
            radius: 14
            border.color: window.border
            layer.enabled: true
            layer.effect: MultiEffect {
                shadowEnabled: true
                shadowColor: "#99000000"
                shadowBlur: 0.55
                shadowVerticalOffset: 7
                shadowHorizontalOffset: 0
            }
        }
        Overlay.modal: Rectangle {
            color: "#66000000"
        }
        header: Rectangle {
            implicitHeight: 38
            color: window.panelRaised
            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 8
                anchors.rightMargin: 8
                spacing: 8
                Image {
                    source: "../assets/FSICO.png"
                    sourceSize.width: 18
                    sourceSize.height: 18
                    Layout.preferredWidth: 18
                    Layout.preferredHeight: 18
                    fillMode: Image.PreserveAspectFit
                }
                Text {
                    text: themedDialog.title
                    color: window.textMain
                    font.pixelSize: 13
                    font.bold: true
                    Layout.fillWidth: true
                    verticalAlignment: Text.AlignVCenter
                }
                Rectangle {
                    id: dialogCloseButton
                    Layout.preferredWidth: 26
                    Layout.preferredHeight: 26
                    radius: 6
                    color: dialogCloseHover.containsMouse ? window.panel : "transparent"
                    Text {
                        anchors.fill: parent
                        text: "×"
                        color: window.textMain
                        font.pixelSize: 19
                        horizontalAlignment: Text.AlignHCenter
                        verticalAlignment: Text.AlignVCenter
                    }
                    MouseArea {
                        id: dialogCloseHover
                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onClicked: themedDialog.reject()
                    }
                }
            }
        }
        footer: Item {
            width: themedDialog.width
            implicitHeight: 64
            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 18
                anchors.rightMargin: 18
                anchors.topMargin: 4
                anchors.bottomMargin: 12
                spacing: 8
                Item {
                    Layout.fillWidth: true
                }
                DialogActionButton {
                    visible: themedDialog.showCancel
                    text: "Cancel"
                    primary: false
                    onClicked: themedDialog.reject()
                }
                DialogActionButton {
                    text: themedDialog.closeOnly ? "Close" : themedDialog.acceptText
                    primary: true
                    onClicked: {
                        if (themedDialog.closeOnly)
                            themedDialog.close();
                        else
                            themedDialog.accept();
                    }
                }
            }
        }
    }

    component DarkField: TextField {
        color: window.textMain
        placeholderTextColor: "#7e898e"
        selectByMouse: true
        font.pixelSize: 14
        implicitHeight: 30
        leftPadding: 13
        background: Rectangle {
            radius: window.buttonRadius
            color: window.lightAppearance ? "#ffffff" : "#0c0d0e"
            border.width: parent.activeFocus ? 1.5 : 1
            border.color: parent.activeFocus ? window.accent : window.border
            Behavior on border.color {
                ColorAnimation {
                    duration: 140
                }
            }
        }
    }

    component EmptyResultsState: Column {
        property string title: "No results yet"
        property string description: "Run a search or scan to populate this view."
        width: 340
        spacing: 7
        Item {
            width: 54
            height: 48
            anchors.horizontalCenter: parent.horizontalCenter
            Text {
                anchors.centerIn: parent
                text: "🖿"
                color: window.textMuted
                opacity: 0.68
                font.family: "Segoe UI Emoji"
                font.pixelSize: 34
            }
            Text {
                anchors.right: parent.right
                anchors.bottom: parent.bottom
                text: "\uE721"
                color: "#28a8f5"
                font.family: "Segoe MDL2 Assets"
                font.pixelSize: 24
            }
        }
        Text {
            anchors.horizontalCenter: parent.horizontalCenter
            text: parent.title
            color: window.textMain
            font.pixelSize: 14
            font.bold: true
        }
        Text {
            width: parent.width
            anchors.horizontalCenter: parent.horizontalCenter
            text: parent.description
            color: window.textMuted
            font.pixelSize: 12
            horizontalAlignment: Text.AlignHCenter
            wrapMode: Text.WordWrap
        }
    }

    component CalendarDateField: Item {
        id: calendarDateField
        property alias text: dateInput.text
        property string placeholderText: ""
        property string dateKey: ""
        property int conditionIndex: -1
        property string dateProperty: ""
        signal textEdited(string value)
        implicitHeight: 34

        function openCalendar(anchorItem) {
            if (conditionIndex >= 0)
                window.openRuleDatePicker(conditionIndex, dateProperty, dateInput.text, anchorItem)
            else
                window.openSearchDatePicker(dateKey, dateInput.text, anchorItem)
        }

        DarkField {
            id: dateInput
            anchors.fill: parent
            rightPadding: calendarGlyph.width + 12
            placeholderText: calendarDateField.placeholderText
            ToolTip.visible: activeFocus
            ToolTip.text: "Date format: MM-DD-YYYY"
            onTextEdited: calendarDateField.textEdited(text)

            // Keep the field editable while making a click anywhere open its calendar.
            TapHandler {
                onTapped: calendarDateField.openCalendar(calendarGlyph)
            }
        }

        AppButton {
            id: calendarGlyph
            width: 30
            height: 30
            anchors.right: parent.right
            anchors.rightMargin: 2
            anchors.verticalCenter: parent.verticalCenter
            text: "\uE787"
            font.family: "Segoe MDL2 Assets"
            ToolTip.text: "Choose date"
            contentItem: Text {
                text: calendarGlyph.text
                color: window.textMuted
                font.family: calendarGlyph.font.family
                font.pixelSize: 14
                horizontalAlignment: Text.AlignHCenter
                verticalAlignment: Text.AlignVCenter
            }
            background: Rectangle {
                radius: window.buttonRadius
                color: calendarGlyph.hovered ? window.panelRaised : "transparent"
                border.color: "transparent"
            }
            onClicked: calendarDateField.openCalendar(calendarGlyph)
        }
    }

    component OrganizerComboBox: ComboBox {
        id: organizerCombo
        implicitHeight: 30
        indicator: Text {
            x: organizerCombo.width - width - 10
            y: (organizerCombo.height - height) / 2
            text: "▾"
            color: window.textMuted
            font.pixelSize: 14
            verticalAlignment: Text.AlignVCenter
        }
        contentItem: Text {
            leftPadding: 10
            rightPadding: 26
            text: organizerCombo.displayText
            color: window.textMain
            font.pixelSize: 13
            verticalAlignment: Text.AlignVCenter
            elide: Text.ElideRight
        }
        background: Rectangle {
            radius: window.buttonRadius
            color: window.panelRaised
            border.color: organizerCombo.activeFocus ? window.accent : window.border
        }
        delegate: ItemDelegate {
            required property int index
            width: organizerCombo.width
            implicitHeight: 36
            text: organizerCombo.textAt(index)
            highlighted: organizerCombo.highlightedIndex === index
            contentItem: Text {
                text: parent.text
                color: window.textMain
                font.pixelSize: 13
                verticalAlignment: Text.AlignVCenter
                leftPadding: 12
                rightPadding: 12
                elide: Text.ElideRight
            }
            background: Rectangle {
                radius: 6
                color: parent.highlighted ? (window.lightAppearance ? "#e7e3dc" : "#242729") : "transparent"
            }
        }
        popup: Popup {
            y: organizerCombo.height + 4
            width: organizerCombo.width
            implicitHeight: Math.min(contentItem.implicitHeight + 16, 280)
            padding: 8
            contentItem: ListView {
                clip: true
                implicitHeight: contentHeight
                model: organizerCombo.popup.visible ? organizerCombo.delegateModel : null
                delegate: organizerCombo.delegate
                currentIndex: organizerCombo.highlightedIndex
                ScrollIndicator.vertical: ScrollIndicator {}
            }
            background: Rectangle {
                radius: 9
                color: window.panelRaised
                border.color: window.border
            }
        }
    }

    RowLayout {
        anchors.fill: parent
        spacing: 0
        layer.enabled: window.modalDialogVisible
        layer.effect: MultiEffect {
            blurEnabled: true
            blur: 0.72
            blurMax: 18
            autoPaddingEnabled: false
        }
        Rectangle {
            Layout.preferredWidth: window.sidebarWidth
            Layout.fillHeight: true
            clip: true
            color: window.lightAppearance ? "#eeece8" : "#0d0e0f"
            border.color: window.border
            border.width: 0
            ColumnLayout {
                anchors.fill: parent
                anchors.topMargin: 14
                anchors.leftMargin: window.sidebarCollapsed ? 8 : 16
                anchors.rightMargin: window.sidebarCollapsed ? 8 : 16
                anchors.bottomMargin: window.sidebarCollapsed ? 8 : 16
                spacing: 14
                RowLayout {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 38
                    Layout.minimumHeight: 38
                    spacing: 8
                    Rectangle {
                        opacity: window.sidebarCollapsed ? 0 : 1
                        visible: opacity > 0
                        Behavior on opacity {
                            NumberAnimation {
                                duration: 170
                                easing.type: window.sidebarCollapsed ? Easing.InCubic : Easing.OutCubic
                            }
                        }
                        width: 38
                        height: 38
                        Layout.preferredWidth: 38
                        Layout.preferredHeight: 38
                        radius: 12
                        color: "#253a3e"
                        border.color: "#367e7b"
                        Image {
                            anchors.fill: parent
                            anchors.margins: 2
                            source: "../assets/FSICO.png"
                            fillMode: Image.PreserveAspectFit
                        }
                    }
                    ColumnLayout {
                        opacity: window.sidebarCollapsed ? 0 : 1
                        visible: opacity > 0
                        Behavior on opacity {
                            NumberAnimation {
                                duration: 170
                                easing.type: window.sidebarCollapsed ? Easing.InCubic : Easing.OutCubic
                            }
                        }
                        Layout.fillWidth: true
                        spacing: 0
                        Text {
                            text: "FileSense"
                            color: window.textMain
                            font.pixelSize: 18
                            font.bold: true
                            Layout.preferredHeight: 30
                            Layout.alignment: Qt.AlignVCenter
                            verticalAlignment: Text.AlignVCenter
                        }
                    }
                    AppButton {
                        id: sidebarToggle
                        Layout.preferredWidth: window.sidebarCollapsed ? 48 : 30
                        Layout.preferredHeight: 30
                        Layout.fillWidth: window.sidebarCollapsed
                        Layout.alignment: Qt.AlignRight | Qt.AlignVCenter
                        padding: 0
                        contentItem: Text {
                            text: "\uE700"
                            color: window.textMuted
                            font.family: "Segoe MDL2 Assets"
                            font.pixelSize: 18
                            horizontalAlignment: Text.AlignHCenter
                            verticalAlignment: Text.AlignVCenter
                        }
                        background: Rectangle {
                            radius: window.buttonRadius
                            color: sidebarToggle.hovered ? window.panelRaised : "transparent"
                        }
                        onClicked: {
                            window.sidebarCollapsed = !window.sidebarCollapsed;
                            window.sidebarWidth = window.sidebarCollapsed ? 72 : 300;
                            window.sidebarIconCellWidth = window.sidebarCollapsed ? 56 : 28;
                        }
                    }
                }
                Rectangle {
                    Layout.fillWidth: true
                    height: 1
                    color: window.border
                }
                ListView {
                    id: navList
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    Layout.topMargin: 5
                    model: window.pages.slice(0, 7)
                    currentIndex: {
                        for (var pageIndex = 0; pageIndex < model.length; ++pageIndex) {
                            if (model[pageIndex].name === window.activePage)
                                return pageIndex;
                        }
                        return -1;
                    }
                    highlightFollowsCurrentItem: true
                    highlight: Rectangle {
                        width: navList.width
                        height: 44
                        color: "transparent"
                        z: 2
                        Rectangle {
                            width: 3
                            height: 20
                            radius: 2
                            color: window.accent
                            anchors.left: parent.left
                            anchors.verticalCenter: parent.verticalCenter
                        }
                        Behavior on y {
                            SpringAnimation {
                                spring: 4.0
                                damping: 0.28
                                mass: 1.0
                                epsilon: 0.001
                            }
                        }
                    }
                    clip: true
                    spacing: 5
                    delegate: Rectangle {
                        required property var modelData
                        width: navList.width
                        height: 44
                        radius: 10
                        color: window.activePage === modelData.name ? (window.lightAppearance ? "#e7e3dc" : "#1c1f21") : navHover.containsMouse ? window.panelRaised : "transparent"
                        border.color: window.activePage === modelData.name ? window.border : "transparent"
                        Behavior on color {
                            ColorAnimation {
                                duration: 140
                            }
                        }
                        RowLayout {
                            anchors.fill: parent
                            anchors.leftMargin: window.sidebarCollapsed ? 0 : 12
                            anchors.rightMargin: window.sidebarCollapsed ? 0 : 10
                            spacing: window.sidebarCollapsed ? 0 : 12
                            Text {
                                text: modelData.icon
                                color: window.activePage === modelData.name ? window.accent : window.textMuted
                                font.family: "Segoe MDL2 Assets"
                                font.pixelSize: 18
                                font.bold: true
                                Layout.preferredWidth: window.sidebarCollapsed ? 0 : window.sidebarIconCellWidth
                                Layout.fillWidth: window.sidebarCollapsed
                                Layout.preferredHeight: 28
                                Layout.alignment: Qt.AlignVCenter
                                horizontalAlignment: Text.AlignHCenter
                                verticalAlignment: Text.AlignVCenter
                            }
                            Text {
                                text: modelData.name
                                opacity: window.sidebarCollapsed ? 0 : 1
                                visible: opacity > 0
                                Behavior on opacity {
                                    NumberAnimation {
                                        duration: 170
                                        easing.type: window.sidebarCollapsed ? Easing.InCubic : Easing.OutCubic
                                    }
                                }
                                color: window.activePage === modelData.name ? window.textMain : window.textMuted
                                font.pixelSize: 14
                                font.weight: window.activePage === modelData.name ? Font.DemiBold : Font.Normal
                                Layout.fillWidth: true
                                verticalAlignment: Text.AlignVCenter
                            }
                        }
                        MouseArea {
                            id: navHover
                            anchors.fill: parent
                            hoverEnabled: true
                            cursorShape: Qt.PointingHandCursor
                            onClicked: {
                                window.activePage = modelData.name;
                                fileSense.navigate(modelData.name);
                            }
                        }
                    }
                }
                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 5
                    Repeater {
                        model: window.pages.slice(7)
                        delegate: Rectangle {
                            required property var modelData
                            Layout.fillWidth: true
                            Layout.preferredHeight: 44
                            radius: 10
                            color: window.activePage === modelData.name ? (window.lightAppearance ? "#e7e3dc" : "#1c1f21") : bottomNavHover.containsMouse ? window.panelRaised : "transparent"
                            RowLayout {
                                anchors.fill: parent
                                anchors.leftMargin: window.sidebarCollapsed ? 0 : 12
                                anchors.rightMargin: window.sidebarCollapsed ? 0 : 10
                                spacing: window.sidebarCollapsed ? 0 : 12
                                Text {
                                    text: modelData.icon
                                    color: window.activePage === modelData.name ? window.accent : window.textMuted
                                    font.family: "Segoe MDL2 Assets"
                                    font.pixelSize: 18
                                    font.bold: true
                                    Layout.preferredWidth: window.sidebarCollapsed ? 0 : window.sidebarIconCellWidth
                                    Layout.fillWidth: window.sidebarCollapsed
                                    Layout.preferredHeight: 28
                                    Layout.alignment: Qt.AlignVCenter
                                    horizontalAlignment: Text.AlignHCenter
                                    verticalAlignment: Text.AlignVCenter
                                }
                                Text {
                                    text: modelData.name
                                    opacity: window.sidebarCollapsed ? 0 : 1
                                    visible: opacity > 0
                                    Behavior on opacity {
                                        NumberAnimation {
                                            duration: 170
                                        easing.type: window.sidebarCollapsed ? Easing.InCubic : Easing.OutCubic
                                        }
                                    }
                                    color: window.activePage === modelData.name ? window.textMain : window.textMuted
                                    font.pixelSize: 14
                                    Layout.fillWidth: true
                                    verticalAlignment: Text.AlignVCenter
                                }
                            }
                            MouseArea {
                                id: bottomNavHover
                                anchors.fill: parent
                                hoverEnabled: true
                                cursorShape: Qt.PointingHandCursor
                                onClicked: {
                                    window.activePage = modelData.name;
                                    fileSense.navigate(modelData.name);
                                }
                            }
                        }
                    }
                }
            }
        }

        ColumnLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 0
            Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: window.activePage === "Home" ? 54 : 62
                color: window.color
                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: 28
                    anchors.rightMargin: 28
                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 9
                        Text {
                            text: window.iconForPage(window.activePage)
                            color: window.accent
                            font.family: "Segoe MDL2 Assets"
                            font.pixelSize: 17
                            Layout.preferredWidth: 28
                            horizontalAlignment: Text.AlignHCenter
                            verticalAlignment: Text.AlignVCenter
                        }
                        Text {
                            id: pageHeadingText
                            text: window.activePage
                            color: window.textMain
                            font.pixelSize: window.activePage === "Home" ? 19 : 21
                            font.weight: Font.DemiBold
                            Layout.fillWidth: true
                            verticalAlignment: Text.AlignVCenter
                        }
                    }
                    Rectangle {
                        id: licenseBadge
                        radius: 9
                        color: window.panel
                        border.color: window.border
                        implicitWidth: 190
                        implicitHeight: 34
                        Row {
                            anchors.centerIn: parent
                            spacing: 7
                            Text {
                                text: "●"
                                color: "#74ddad"
                                font.pixelSize: 10
                                anchors.verticalCenter: parent.verticalCenter
                            }
                            Text {
                                text: fileSense.licenseLabel
                                color: window.textMuted
                                font.pixelSize: 12
                                anchors.verticalCenter: parent.verticalCenter
                            }
                        }
                    }
                    Loader {
                        visible: fileSense.licenseLabel !== "Activated"
                        sourceComponent: coffeeButton
                        onLoaded: {
                            item.text = "☕ Buy me a Coffee";
                            item.clicked.connect(function () {
                                activationDialog.open();
                            });
                        }
                    }
                    AppButton {
                        id: appearanceButton
                        visible: false
                        implicitWidth: 34
                        implicitHeight: 34
                        padding: 0
                        enabled: false
                        opacity: 0.5
                        ToolTip.text: "Appearance options will be available in a future version"
                        ToolTip.visible: hovered
                        contentItem: Text {
                            text: window.lightAppearance ? "☾" : "☀"
                            color: window.textMain
                            font.pixelSize: 17
                            verticalAlignment: Text.AlignVCenter
                            horizontalAlignment: Text.AlignHCenter
                        }
                        background: Rectangle {
                            radius: width / 2
                            color: window.panelRaised
                            border.color: window.border
                        }
                        onClicked: fileSense.toggleAppearance()
                    }
                }
                Rectangle {
                    anchors.left: parent.left
                    anchors.leftMargin: 28
                    anchors.bottom: parent.bottom
                    width: Math.min(parent.width - 56, pageHeadingText.implicitWidth + 37)
                    height: 2
                    radius: 2
                    color: "#1689ef"
                }
            }

            Flickable {
                id: contentScroll
                Layout.fillWidth: true
                Layout.fillHeight: true
                clip: true
                contentWidth: width
                contentHeight: contentColumn.implicitHeight + 48
                ScrollBar.vertical: ScrollBar {
                    policy: ScrollBar.AsNeeded
                }
                ColumnLayout {
                    id: contentColumn
                    width: contentScroll.width - 56
                    anchors.horizontalCenter: parent.horizontalCenter
                    anchors.top: parent.top
                    anchors.topMargin: window.activePage === "Home" ? 12 : 24
                    spacing: window.activePage === "Home" ? 9 : 18
                    opacity: 1
                    Behavior on opacity {
                        NumberAnimation {
                            duration: 160
                        }
                    }

                    Rectangle {
                        visible: window.activePage === "Home"
                        id: homeHero
                        Layout.fillWidth: true
                        Layout.preferredHeight: 104
                        radius: 12
                        color: window.lightAppearance ? window.panel : "#151719"
                        border.color: window.border
                        clip: true
                        Image {
                            id: homeHeroWatermark
                            source: "../assets/home/hero-folder-watermark.png"
                            fillMode: Image.PreserveAspectFit
                            horizontalAlignment: Image.AlignRight
                            width: 300
                            height: 190
                            anchors.right: parent.right
                            anchors.rightMargin: 0
                            anchors.verticalCenter: parent.verticalCenter
                            opacity: 0.15
                            z: 0
                        }
                        RowLayout {
                            anchors.fill: parent
                            anchors.leftMargin: 22
                            anchors.rightMargin: 22
                            spacing: 16
                            z: 1
                            Rectangle {
                                Layout.preferredWidth: 66
                                Layout.preferredHeight: 66
                                radius: 15
                                color: "#173d50"
                                border.color: "#247da3"
                                Image {
                                    anchors.fill: parent
                                    anchors.margins: 3
                                    source: "../assets/FSICO.png"
                                    fillMode: Image.PreserveAspectFit
                                }
                            }
                            Rectangle {
                                Layout.preferredWidth: 1
                                Layout.preferredHeight: 66
                                color: "#58616b"
                                opacity: 0.7
                            }
                            ColumnLayout {
                                Layout.alignment: Qt.AlignVCenter
                                spacing: 4
                                Text {
                                    text: "<b>File</b><span style='color:#2498f6'>Sense</span>"
                                    textFormat: Text.RichText
                                    color: window.textMain
                                    font.pixelSize: 25
                                    font.bold: true
                                }
                                Text {
                                    text: "One smarter way to manage your PC."
                                    color: window.textMuted
                                    font.pixelSize: 13
                                }
                            }
                            Item { Layout.fillWidth: true }
                            ColumnLayout {
                                Layout.alignment: Qt.AlignVCenter
                                spacing: 0
                                Text {
                                    text: "Organize  <span style='color:#2498f6'>•</span>  Clean  <span style='color:#2498f6'>•</span>  Optimize"
                                    textFormat: Text.RichText
                                    color: window.textMuted
                                    font.pixelSize: 12
                                    font.bold: true
                                    Layout.alignment: Qt.AlignRight
                                }
                            }
                        }
                    }

                    RowLayout {
                        visible: window.activePage === "Home"
                        Layout.fillWidth: true
                        Layout.preferredHeight: 22
                        spacing: 7
                        Rectangle {
                            Layout.preferredWidth: 4
                            Layout.preferredHeight: 20
                            radius: 3
                            color: "#1689ef"
                        }
                        Text {
                            text: "Explore FileSense"
                            color: window.textMain
                            font.pixelSize: 16
                            font.bold: true
                        }
                        Item { Layout.fillWidth: true }
                        Rectangle {
                            Layout.preferredWidth: 22
                            Layout.preferredHeight: 1
                            color: window.textMuted
                        }
                        Text {
                            text: "Quick access to all powerful tools"
                            color: window.textMuted
                            font.pixelSize: 12
                        }
                    }

                    GridLayout {
                        visible: window.activePage === "Home"
                        Layout.fillWidth: true
                        columns: 3
                        columnSpacing: 9
                        rowSpacing: 9
                        Repeater {
                            model: [
                                {
                                    title: "File Organizer",
                                    desc: "Sort files into categories or build your own organization rules.",
                                    action: "Organize files",
                                    icon: window.iconForPage("File Organizer"), tint: "#1689ef", image: "file-organizer.png"
                                },
                                {
                                    title: "Storage Analyzer",
                                    desc: "See which folders and file types use the most space.",
                                    action: "Analyze storage",
                                    icon: window.iconForPage("Storage Analyzer"), tint: "#20bd66", image: "storage-analyzer.png"
                                },
                                {
                                    title: "File Search & Finder",
                                    desc: "Find files by name, extension, type, size, or date.",
                                    action: "Search files",
                                    icon: window.iconForPage("File Search & Finder"), tint: "#7651ee", image: "file-search.png"
                                },
                                {
                                    title: "Duplicate Finder",
                                    desc: "Find repeated files and review them before acting.",
                                    action: "Find duplicates",
                                    icon: window.iconForPage("Duplicate Finder"), tint: "#eaa11c", image: "duplicate-finder.png"
                                },
                                {
                                    title: "Junk Cleaner",
                                    desc: "Inspect cleanup candidates by safe, separate categories.",
                                    action: "Review cleanup",
                                    icon: window.iconForPage("Junk Cleaner"), tint: "#03aed0", image: "junk-cleaner.png"
                                },
                                {
                                    title: "Startup Manager",
                                    desc: "Review apps, tasks, services, and policies that run at startup.",
                                    action: "Review startup",
                                    icon: window.iconForPage("Startup Manager"), tint: "#7555ee", image: "startup-manager.png"
                                }
                            ]
                            delegate: Rectangle {
                                required property var modelData
                                Layout.fillWidth: true
                                Layout.preferredHeight: 132
                                radius: 12
                                color: window.lightAppearance ? window.panel : "#17191c"
                                border.color: window.border
                                gradient: Gradient {
                                    GradientStop { position: 0; color: window.lightAppearance ? window.panel : "#191b1f" }
                                    GradientStop { position: 1; color: window.lightAppearance ? window.panel : "#151719" }
                                }
                                Item {
                                    anchors.fill: parent
                                    anchors.margins: 14
                                    Rectangle {
                                        id: homeCardIconTile
                                        width: 68
                                        height: 68
                                        radius: 14
                                        color: homeCardArtwork.status === Image.Ready ? "transparent" : modelData.tint
                                        opacity: 0.92
                                        anchors.left: parent.left
                                        anchors.top: parent.top
                                        Image {
                                            id: homeCardArtwork
                                            anchors.fill: parent
                                            source: modelData.image ? "../assets/home/" + modelData.image : ""
                                            fillMode: Image.PreserveAspectFit
                                            visible: status === Image.Ready
                                        }
                                        Text {
                                            anchors.centerIn: parent
                                            text: modelData.icon
                                            color: "#f4f8ff"
                                            font.family: "Segoe MDL2 Assets"
                                            font.pixelSize: 42
                                            font.bold: true
                                            visible: homeCardArtwork.status !== Image.Ready
                                        }
                                    }
                                    Text {
                                        id: homeCardTitle
                                        text: modelData.title
                                        color: window.textMain
                                        font.pixelSize: 14
                                        font.bold: true
                                        anchors.left: homeCardIconTile.right
                                        anchors.leftMargin: 12
                                        anchors.right: homeCardArrow.left
                                        anchors.rightMargin: 8
                                        anchors.top: parent.top
                                        elide: Text.ElideRight
                                    }
                                    Text {
                                        id: homeCardDescription
                                        text: modelData.desc
                                        color: window.textMuted
                                        font.pixelSize: 12
                                        wrapMode: Text.WordWrap
                                        anchors.top: homeCardTitle.bottom
                                        anchors.topMargin: 4
                                        anchors.left: homeCardTitle.left
                                        anchors.right: homeCardArrow.left
                                        anchors.rightMargin: 8
                                        verticalAlignment: Text.AlignTop
                                    }
                                    AppButton {
                                        anchors.left: homeCardTitle.left
                                        anchors.bottom: parent.bottom
                                        width: 124
                                        text: modelData.action
                                        implicitHeight: 28
                                        leftPadding: 12
                                        rightPadding: 12
                                        font.pixelSize: 12
                                        font.bold: true
                                        contentItem: Text {
                                            text: parent.text
                                            color: "#06131b"
                                            font: parent.font
                                            horizontalAlignment: Text.AlignHCenter
                                            verticalAlignment: Text.AlignVCenter
                                        }
                                        background: Rectangle {
                                            radius: 7
                                            color: parent.down ? Qt.darker(modelData.tint, 1.12) : modelData.tint
                                        }
                                        onClicked: {
                                            window.activePage = modelData.title;
                                            fileSense.navigate(modelData.title);
                                        }
                                    }
                                    AppButton {
                                        id: homeCardArrow
                                        width: 26
                                        height: 26
                                        anchors.top: parent.top
                                        anchors.right: parent.right
                                        text: ""
                                        padding: 0
                                        contentItem: Item {
                                            Text {
                                                anchors.centerIn: parent
                                                text: "\uE72A"
                                                color: window.textMain
                                                font.family: "Segoe MDL2 Assets"
                                                font.pixelSize: 15
                                                font.bold: true
                                            }
                                        }
                                        background: Rectangle {
                                            radius: width / 2
                                            color: parent.hovered ? "#3a414c" : "#292d35"
                                        }
                                        onClicked: {
                                            window.activePage = modelData.title;
                                            fileSense.navigate(modelData.title);
                                        }
                                    }
                                }
                            }
                        }
                    }

                    Rectangle {
                        id: searchControlsCard
                        visible: window.activePage === "File Search & Finder"
                        Layout.fillWidth: true
                        Layout.preferredHeight: window.searchFiltersExpanded
                                                ? Math.max(380, 346 + (searchExcludedFolders.count > 0 ? Math.max(30, searchExcludedFlow.implicitHeight) : 0))
                                                : 204
                        Component.onCompleted: {
                            if (!searchRoots.text) searchRoots.text = fileSense.savedSearchLocations;
                            if (searchExcludedFolders.count === 0 && fileSense.savedSearchExclusions) {
                                var savedExclusions = fileSense.savedSearchExclusions.split(";");
                                for (var i = 0; i < savedExclusions.length; ++i) {
                                    var savedPath = savedExclusions[i].trim();
                                    if (savedPath) addSearchExcludedFolder(savedPath);
                                }
                            }
                        }
                        radius: 16
                        color: window.panel
                        border.color: window.border
                        ColumnLayout {
                            anchors.fill: parent
                            anchors.margins: 18
                            spacing: 9
                            RowLayout {
                                Layout.fillWidth: true
                                spacing: 9
                                Text {
                                    text: "🖿"
                                    color: window.accent
                                    font.family: "Segoe UI Emoji"
                                    font.pixelSize: 16
                                }
                                Text {
                                    text: "Search Location"
                                    color: window.textMain
                                    font.pixelSize: 15
                                    font.bold: true
                                }
                                Item { Layout.fillWidth: true }
                            }
                            RowLayout {
                                id: searchLocationRow
                                Layout.fillWidth: true
                                spacing: 10
                                Item {
                                    Layout.fillWidth: true
                                    Layout.minimumWidth: 140
                                    Layout.preferredHeight: 34
                                    DarkField {
                                        id: searchRoots
                                        anchors.fill: parent
                                        leftPadding: 36
                                        rightPadding: 34
                                        placeholderText: "Drive or folder paths separated by ;"
                                    }
                                    Text {
                                        anchors.left: parent.left
                                        anchors.leftMargin: 11
                                        anchors.verticalCenter: parent.verticalCenter
                                        text: "🖿"
                                        color: window.accent
                                        font.family: "Segoe UI Emoji"
                                        font.pixelSize: 15
                                    }
                                    Rectangle {
                                        visible: searchRoots.text.length > 0
                                        width: 24
                                        height: 24
                                        radius: 12
                                        anchors.right: parent.right
                                        anchors.rightMargin: 5
                                        anchors.verticalCenter: parent.verticalCenter
                                        color: clearSearchRootsHover.containsMouse ? window.panelRaised : "transparent"
                                        Text { anchors.centerIn: parent; text: "×"; color: window.textMuted; font.pixelSize: 18 }
                                        MouseArea {
                                            id: clearSearchRootsHover
                                            anchors.fill: parent
                                            hoverEnabled: true
                                            cursorShape: Qt.PointingHandCursor
                                            onClicked: searchRoots.clear()
                                        }
                                    }
                                }
                                ComboBox {
                                    id: searchDriveBox
                                    Layout.preferredWidth: 190
                                    Layout.preferredHeight: 34
                                    model: fileSense.drives
                                    textRole: "label"
                                    valueRole: "path"
                                    indicator: Text {
                                        x: searchDriveBox.width - width - 10
                                        y: (searchDriveBox.height - height) / 2
                                        text: "▾"
                                        color: window.textMuted
                                        font.pixelSize: 14
                                        verticalAlignment: Text.AlignVCenter
                                    }
                                    contentItem: Text {
                                        leftPadding: 32
                                        text: searchDriveBox.displayText || "Select drive"
                                        color: window.textMain
                                        verticalAlignment: Text.AlignVCenter
                                        elide: Text.ElideRight
                                    }
                                    background: Rectangle {
                                        radius: window.buttonRadius
                                        color: window.panelRaised
                                        border.color: window.border
                                    }
                                    Text {
                                        anchors.left: parent.left
                                        anchors.leftMargin: 10
                                        anchors.verticalCenter: parent.verticalCenter
                                        text: "\uEDA2"
                                        color: window.textMuted
                                        font.family: "Segoe MDL2 Assets"
                                        font.pixelSize: 14
                                    }
                                }
                                Loader {
                                    id: searchAddDriveControl
                                    sourceComponent: actionButton
                                    onLoaded: {
                                        item.iconText = "\uEDA2";
                                        item.text = "Add Drive";
                                        item.clicked.connect(function () {
                                            if (searchDriveBox.currentValue) appendSearchLocation(searchDriveBox.currentValue);
                                        });
                                    }
                                }
                                Loader {
                                    id: searchBrowseControl
                                    sourceComponent: actionButton
                                    onLoaded: {
                                        item.iconText = "🖿";
                                        item.iconFontFamily = "Segoe UI Emoji";
                                        item.text = "Browse";
                                        item.clicked.connect(function () {
                                            folderDialog.target = "search";
                                            folderDialog.open();
                                        });
                                    }
                                }
                                Item {
                                    Layout.preferredWidth: 190
                                    Layout.minimumWidth: 190
                                    Layout.maximumWidth: 190
                                    Layout.preferredHeight: 34
                                    CheckBox {
                                        id: searchIncludeSubfolders
                                        anchors.verticalCenter: parent.verticalCenter
                                        text: "Include subfolders"
                                        checked: false
                                        width: parent.width
                                        height: 24
                                        implicitWidth: 23 + searchIncludeLabel.implicitWidth
                                        padding: 0
                                        leftPadding: 26
                                        rightPadding: 0
                                        contentItem: Text {
                                            id: searchIncludeLabel
                                            text: searchIncludeSubfolders.text
                                            color: window.textMain
                                            font.pixelSize: 13
                                            verticalAlignment: Text.AlignVCenter
                                        }
                                        indicator: Rectangle {
                                            x: 0
                                            y: (searchIncludeSubfolders.height - height) / 2
                                            implicitWidth: 19
                                            implicitHeight: 19
                                            radius: 4
                                            color: searchIncludeSubfolders.checked ? window.accent : (window.lightAppearance ? "#ffffff" : "#111315")
                                            border.width: 1
                                            border.color: searchIncludeSubfolders.checked ? window.accent : window.textMuted
                                            Text {
                                                anchors.centerIn: parent
                                                text: "✓"
                                                visible: searchIncludeSubfolders.checked
                                                color: "#102321"
                                                font.pixelSize: 12
                                            }
                                        }
                                        ToolTip.visible: hovered
                                        ToolTip.text: "For folder paths, search subfolders when checked. Drive roots are always searched recursively."
                                    }
                                }
                            }
                            Rectangle { Layout.fillWidth: true; height: 1; color: window.border }
                            RowLayout {
                                Layout.fillWidth: true
                                spacing: 9
                                Text {
                                    text: "\uE71C"
                                    color: window.accent
                                    font.family: "Segoe MDL2 Assets"
                                    font.pixelSize: 16
                                }
                                Text {
                                    text: "Search Filters"
                                    color: window.textMain
                                    font.pixelSize: 15
                                    font.bold: true
                                }
                                Text {
                                    visible: window.searchFiltersExpanded
                                    text: "All filters are optional; select at least one to search."
                                    color: window.textMuted
                                    font.pixelSize: 12
                                    elide: Text.ElideRight
                                    Layout.fillWidth: true
                                    Layout.maximumWidth: 440
                                }
                                Item { Layout.fillWidth: true }
                                Item {
                                    Layout.preferredWidth: 28
                                    Layout.preferredHeight: 26
                                    Text {
                                        anchors.centerIn: parent
                                        text: "▾"
                                        color: window.textMuted
                                        font.pixelSize: 17
                                    }
                                    MouseArea {
                                        anchors.fill: parent
                                        cursorShape: Qt.PointingHandCursor
                                        onClicked: window.searchFiltersExpanded = !window.searchFiltersExpanded
                                    }
                                }
                            }
                            RowLayout {
                                visible: window.searchFiltersExpanded
                                Layout.fillWidth: true
                                spacing: 9
                                ColumnLayout {
                                    Layout.fillWidth: true
                                    Layout.preferredWidth: 500
                                    Layout.minimumWidth: 220
                                    spacing: 4
                                    Text { text: "File name contains"; color: window.textMuted; font.pixelSize: 13 }
                                    DarkField {
                                        id: searchName
                                        Layout.fillWidth: true
                                        Layout.preferredHeight: 32
                                        placeholderText: "e.g. report, invoice, project"
                                    }
                                }
                                ColumnLayout {
                                    Layout.fillWidth: true
                                    Layout.preferredWidth: 500
                                    Layout.minimumWidth: 220
                                    spacing: 4
                                    Text { text: "File extensions"; color: window.textMuted; font.pixelSize: 13 }
                                    DarkField {
                                        id: searchExt
                                        Layout.fillWidth: true
                                        Layout.preferredHeight: 32
                                        placeholderText: "pdf, jpg"
                                    }
                                }
                                ColumnLayout {
                                    Layout.preferredWidth: 250
                                    Layout.minimumWidth: 220
                                    spacing: 4
                                    Text { text: "File size"; color: window.textMuted; font.pixelSize: 13 }
                                    RowLayout {
                                        Layout.fillWidth: true
                                        spacing: 6
                                        RowLayout {
                                            Layout.fillWidth: true
                                            Layout.preferredWidth: 100
                                            spacing: 4
                                            DarkField {
                                                id: minSize
                                                Layout.fillWidth: true
                                                Layout.preferredWidth: 72
                                                Layout.minimumWidth: 58
                                                Layout.preferredHeight: 32
                                                placeholderText: "Min"
                                                validator: DoubleValidator { bottom: 0 }
                                            }
                                            OrganizerComboBox {
                                                id: minSizeUnit
                                                Layout.preferredWidth: 64
                                                Layout.preferredHeight: 32
                                                model: ["B", "KB", "MB", "GB"]
                                                currentIndex: 2
                                            }
                                        }
                                        Text { text: "–"; color: window.textMuted; font.pixelSize: 14 }
                                        RowLayout {
                                            Layout.fillWidth: true
                                            Layout.preferredWidth: 100
                                            spacing: 4
                                            DarkField {
                                                id: maxSize
                                                Layout.fillWidth: true
                                                Layout.preferredWidth: 72
                                                Layout.minimumWidth: 58
                                                Layout.preferredHeight: 32
                                                placeholderText: "Max"
                                                validator: DoubleValidator { bottom: 0 }
                                            }
                                            OrganizerComboBox {
                                                id: maxSizeUnit
                                                Layout.preferredWidth: 64
                                                Layout.preferredHeight: 32
                                                model: ["B", "KB", "MB", "GB"]
                                                currentIndex: 2
                                            }
                                        }
                                    }
                                }
                            }
                            RowLayout {
                                visible: window.searchFiltersExpanded
                                Layout.fillWidth: true
                                spacing: 8
                                Text {
                                    text: "File types:"
                                    color: window.textMuted
                                    font.pixelSize: 13
                                }
                                Repeater {
                                    id: searchCategoryRepeater
                                    model: ["Compressed", "Video", "Audio", "Images", "Documents", "Programs", "Other"]
                                    delegate: CheckBox {
                                        id: searchCategoryCheckBox
                                        required property string modelData
                                        text: modelData
                                        implicitWidth: 26 + searchCategoryLabel.implicitWidth
                                        implicitHeight: 26
                                        Layout.alignment: Qt.AlignVCenter
                                        padding: 0
                                        leftPadding: 25
                                        rightPadding: 0
                                        contentItem: Text {
                                            id: searchCategoryLabel
                                            anchors.fill: parent
                                            anchors.leftMargin: 25
                                            anchors.rightMargin: 6
                                            text: searchCategoryCheckBox.text
                                            color: window.textMain
                                            font.pixelSize: 13
                                            verticalAlignment: Text.AlignVCenter
                                        }
                                        indicator: Rectangle {
                                            x: 0
                                            y: (searchCategoryCheckBox.height - height) / 2
                                            implicitWidth: 18
                                            implicitHeight: 18
                                            radius: 4
                                            color: searchCategoryCheckBox.checked ? window.accent : (window.lightAppearance ? "#ffffff" : "#111315")
                                            border.width: 1
                                            border.color: searchCategoryCheckBox.checked ? window.accent : window.textMuted
                                            Text { anchors.centerIn: parent; text: "✓"; visible: searchCategoryCheckBox.checked; color: "#101112"; font.pixelSize: 12; font.bold: true }
                                        }
                                        background: Rectangle {
                                            color: "transparent"
                                            border.color: "transparent"
                                        }
                                    }
                                }
                            }
                            RowLayout {
                                visible: window.searchFiltersExpanded
                                Layout.fillWidth: true
                                spacing: 8
                                Text { text: "Created date"; color: window.textMuted; font.pixelSize: 13; Layout.preferredWidth: 82; verticalAlignment: Text.AlignVCenter }
                                CalendarDateField {
                                    id: createdFrom
                                    Layout.preferredWidth: 142
                                    Layout.preferredHeight: 34
                                    placeholderText: "Created from"
                                    dateKey: "createdFrom"
                                }
                                CalendarDateField {
                                    id: createdTo
                                    Layout.preferredWidth: 142
                                    Layout.preferredHeight: 34
                                    placeholderText: "Created to"
                                    dateKey: "createdTo"
                                }
                                Text { text: "Modified date"; color: window.textMuted; font.pixelSize: 13; Layout.preferredWidth: 92; verticalAlignment: Text.AlignVCenter }
                                CalendarDateField {
                                    id: modifiedFrom
                                    Layout.preferredWidth: 142
                                    Layout.preferredHeight: 34
                                    placeholderText: "Modified from"
                                    dateKey: "modifiedFrom"
                                }
                                CalendarDateField {
                                    id: modifiedTo
                                    Layout.preferredWidth: 142
                                    Layout.preferredHeight: 34
                                    placeholderText: "Modified to"
                                    dateKey: "modifiedTo"
                                }
                            }
                            RowLayout {
                                Layout.fillWidth: true
                                spacing: 8
                                Item { Layout.fillWidth: true }
                                Item {
                                    id: searchExcludedArea
                                    visible: searchExcludedFolders.count > 0
                                    Layout.fillWidth: visible
                                    Layout.preferredWidth: visible ? 360 : 0
                                    Layout.minimumWidth: visible ? 120 : 0
                                    Layout.preferredHeight: visible ? Math.max(30, searchExcludedFlow.implicitHeight) : 0
                                    Flow {
                                        id: searchExcludedFlow
                                        anchors.left: parent.left
                                        anchors.right: parent.right
                                        anchors.verticalCenter: parent.verticalCenter
                                        spacing: 7
                                        Repeater {
                                            model: searchExcludedFolders
                                            delegate: Rectangle {
                                                required property string path
                                                required property int index
                                                width: Math.min(searchExcludedFlow.width * 0.55, searchChipPath.implicitWidth + 44)
                                                height: 30
                                                radius: 15
                                                color: window.lightAppearance ? "#efede8" : "#202427"
                                                border.color: window.border
                                                Text {
                                                    id: searchChipPath
                                                    anchors.left: parent.left
                                                    anchors.leftMargin: 12
                                                    anchors.right: searchChipRemove.left
                                                    anchors.rightMargin: 4
                                                    anchors.verticalCenter: parent.verticalCenter
                                                    text: path
                                                    color: window.textMain
                                                    font.pixelSize: 11
                                                    elide: Text.ElideMiddle
                                                }
                                                Rectangle {
                                                    id: searchChipRemove
                                                    width: 22
                                                    height: 22
                                                    radius: 11
                                                    anchors.right: parent.right
                                                    anchors.rightMargin: 4
                                                    anchors.verticalCenter: parent.verticalCenter
                                                    color: removeSearchHover.containsMouse ? window.panelRaised : "transparent"
                                                    Text { anchors.centerIn: parent; text: "×"; color: window.textMain; font.pixelSize: 16 }
                                                    MouseArea {
                                                        id: removeSearchHover
                                                        anchors.fill: parent
                                                        hoverEnabled: true
                                                        cursorShape: Qt.PointingHandCursor
                                                        onClicked: searchExcludedFolders.remove(index)
                                                        ToolTip.visible: containsMouse
                                                        ToolTip.text: "Remove excluded folder"
                                                    }
                                                }
                                            }
                                        }
                                    }
                                }
                                Loader {
                                    id: searchExcludeButton
                                    sourceComponent: actionButton
                                    onLoaded: {
                                        item.iconText = "\uE738";
                                        item.text = "Exclude Folder (Optional)";
                                        item.clicked.connect(function () {
                                            folderDialog.target = "searchExclude";
                                            folderDialog.open();
                                        });
                                    }
                                }
                                Loader {
                                    sourceComponent: actionButton
                                    onLoaded: {
                                        item.iconText = "\uE721";
                                        item.text = "Search";
                                        item.clicked.connect(function () {
                                            fileSense.searchFiles(searchRoots.text, searchName.text, searchExt.text, selectedSearchCategories(), minSize.text, maxSize.text,
                                                                  minSizeUnit.currentText, maxSizeUnit.currentText,
                                                                  searchExcludedFolderPaths().join(";"), createdFrom.text, createdTo.text, modifiedFrom.text, modifiedTo.text,
                                                                  searchIncludeSubfolders.checked);
                                        });
                                    }
                                }
                                Loader {
                                    visible: fileSense.searchRunning
                                    sourceComponent: actionButton
                                    onLoaded: {
                                        item.text = "Cancel";
                                        item.clicked.connect(function () { fileSense.cancelSearch(); });
                                    }
                                }
                            }
                        }
                    }

                    Rectangle {
                        visible: window.activePage === "Storage Analyzer"
                        Layout.fillWidth: true
                        Layout.preferredHeight: 86
                        radius: 16
                        color: window.panel
                        border.color: window.border
                        ColumnLayout {
                            anchors.fill: parent
                            anchors.margins: 12
                            spacing: 6
                            RowLayout {
                            Layout.fillWidth: true
                            spacing: 10
                            ComboBox {
                                id: driveBox
                                Layout.preferredWidth: 250
                                Layout.preferredHeight: 30
                                model: fileSense.drives
                                currentIndex: -1
                                textRole: "label"
                                valueRole: "path"
                                onActivated: storagePath.text = currentValue
                                background: Rectangle {
                                    radius: window.buttonRadius
                                    color: window.lightAppearance ? "#ffffff" : "#15181a"
                                    border.color: driveBox.activeFocus ? window.accent : window.border
                                }
                                contentItem: Text {
                                    leftPadding: 12
                                    rightPadding: 28
                                    text: driveBox.currentIndex < 0 ? "Choose a drive" : driveBox.displayText
                                    color: window.textMain
                                    verticalAlignment: Text.AlignVCenter
                                    elide: Text.ElideRight
                                }
                                indicator: Text {
                                    x: driveBox.width - width - 10
                                    y: (driveBox.height - height) / 2
                                    text: "▾"
                                    color: window.textMuted
                                    font.pixelSize: 13
                                }
                                popup: Popup {
                                    y: driveBox.height + 4
                                    width: driveBox.width
                                    implicitHeight: Math.min(contentItem.implicitHeight + 16, 300)
                                    padding: 8
                                    contentItem: ListView {
                                        id: driveOptionsList
                                        clip: true
                                        implicitHeight: contentHeight
                                        model: fileSense.drives
                                        delegate: Rectangle {
                                            required property var modelData
                                            required property int index
                                            width: driveOptionsList.width
                                            height: 34
                                            radius: 6
                                            color: driveOptionMouse.containsMouse ? window.panel : "transparent"
                                            Text {
                                                anchors.fill: parent
                                                anchors.leftMargin: 12
                                                anchors.rightMargin: 10
                                                text: modelData.label || ""
                                                color: window.textMain
                                                font.pixelSize: 12
                                                verticalAlignment: Text.AlignVCenter
                                                elide: Text.ElideRight
                                            }
                                            MouseArea {
                                                id: driveOptionMouse
                                                anchors.fill: parent
                                                hoverEnabled: true
                                                cursorShape: Qt.PointingHandCursor
                                                onClicked: {
                                                    driveBox.currentIndex = index;
                                                    storagePath.text = modelData.path || "";
                                                    driveBox.popup.close();
                                                }
                                            }
                                        }
                                        ScrollIndicator.vertical: ScrollIndicator {}
                                    }
                                    background: Rectangle {
                                        color: window.panelRaised
                                        radius: 10
                                        border.color: window.border
                                    }
                                }
                            }
                            DarkField {
                                id: storagePath
                                Layout.fillWidth: true
                                placeholderText: "Or enter a drive/folder path"
                            }
                            Loader {
                                sourceComponent: actionButton
                                onLoaded: {
                                    item.iconText = "🖿";
                                    item.iconFontFamily = "Segoe UI Emoji";
                                    item.text = "Choose folder";
                                    item.clicked.connect(function () {
                                        folderDialog.target = "storage";
                                        folderDialog.open();
                                    });
                                }
                            }
                            Loader {
                                sourceComponent: actionButton
                                onLoaded: {
                                    item.iconText = "\uE768";
                                    item.text = "Scan storage";
                                    item.clicked.connect(function () {
                                        if (!storagePath.text.trim()) {
                                            storagePathDialog.open();
                                            return;
                                        }
                                        window.storageTreemapPath = "";
                                        fileSense.scanStorage(storagePath.text, "true");
                                    });
                                }
                            }
                            }
                            RowLayout {
                                visible: fileSense.storageScanning
                                Layout.fillWidth: true
                                Layout.preferredHeight: 20
                                spacing: 8
                                Text {
                                    text: fileSense.status
                                    color: window.textMuted
                                    font.pixelSize: 11
                                    elide: Text.ElideMiddle
                                    Layout.fillWidth: true
                                }
                                AnimatedProgressBar {
                                    Layout.preferredWidth: 160
                                    Layout.preferredHeight: 6
                                    running: fileSense.storageScanning
                                    trackColor: window.border
                                }
                            }
                        }
                    }

                    Rectangle {
                        visible: window.activePage === "Storage Analyzer" && fileSense.rows.length > 0
                        Layout.fillWidth: true
                        Layout.preferredHeight: 96
                        radius: 14
                        color: window.panel
                        border.color: window.border
                        RowLayout {
                            anchors.fill: parent
                            anchors.leftMargin: 14
                            anchors.rightMargin: 14
                            spacing: 14
                            Image { source: "../assets/JunkCleaner/drive.png"; sourceSize.width: 40; sourceSize.height: 40; Layout.preferredWidth: 40; Layout.preferredHeight: 40; fillMode: Image.PreserveAspectFit }
                            ColumnLayout {
                                Layout.preferredWidth: 145
                                spacing: 2
                                Text { text: String(fileSense.rows.length > 0 ? ((fileSense.rows[0] || {}).name || "—") : "—"); color: window.textMain; font.pixelSize: 19; font.bold: true; elide: Text.ElideRight }
                                Text { text: fileSense.storageVolumeInfo.filesystem || "Storage volume"; color: window.textMuted; font.pixelSize: 13; elide: Text.ElideRight }
                            }
                            Rectangle { Layout.preferredWidth: 1; Layout.preferredHeight: 60; color: window.border }
                            Image { source: "../assets/JunkCleaner/allocated.png"; sourceSize.width: 38; sourceSize.height: 38; Layout.preferredWidth: 38; Layout.preferredHeight: 38; fillMode: Image.PreserveAspectFit }
                            ColumnLayout {
                                Layout.preferredWidth: 138
                                spacing: 2
                                Text { text: fileSense.storageVolumeInfo.total || "—"; color: window.textMain; font.pixelSize: 19; font.bold: true }
                                Text { text: "Capacity"; color: window.textMuted; font.pixelSize: 13 }
                            }
                            Rectangle { Layout.preferredWidth: 1; Layout.preferredHeight: 60; color: window.border }
                            Image { source: "../assets/JunkCleaner/used.png"; sourceSize.width: 38; sourceSize.height: 38; Layout.preferredWidth: 38; Layout.preferredHeight: 38; fillMode: Image.PreserveAspectFit }
                            ColumnLayout {
                                Layout.preferredWidth: 138
                                spacing: 2
                                Text { text: fileSense.storageVolumeInfo.used || "—"; color: window.textMain; font.pixelSize: 19; font.bold: true }
                                Text { text: "Used Space (" + Number(fileSense.storageVolumeInfo.usedPercent || 0).toFixed(1) + "%)"; color: window.textMuted; font.pixelSize: 13 }
                            }
                            Rectangle { Layout.preferredWidth: 1; Layout.preferredHeight: 60; color: window.border }
                            Image { source: "../assets/JunkCleaner/free.png"; sourceSize.width: 38; sourceSize.height: 38; Layout.preferredWidth: 38; Layout.preferredHeight: 38; fillMode: Image.PreserveAspectFit }
                            ColumnLayout {
                                Layout.preferredWidth: 120
                                spacing: 2
                                Text { text: fileSense.storageVolumeInfo.free || "—"; color: window.textMain; font.pixelSize: 19; font.bold: true }
                                Text { text: "Free Space (" + (100 - Number(fileSense.storageVolumeInfo.usedPercent || 0)).toFixed(1) + "%)"; color: window.textMuted; font.pixelSize: 13 }
                            }
                            Rectangle { Layout.preferredWidth: 1; Layout.preferredHeight: 60; color: window.border }
                            Image { source: "../assets/JunkCleaner/summary.png"; sourceSize.width: 34; sourceSize.height: 34; Layout.preferredWidth: 34; Layout.preferredHeight: 34; fillMode: Image.PreserveAspectFit }
                            ColumnLayout {
                                Layout.fillWidth: true
                                spacing: 2
                                Text { text: "Scan Summary"; color: window.textMain; font.pixelSize: 14; font.bold: true }
                                Text { text: Number(fileSense.rows.length > 0 ? fileSense.rows[0].folders || 0 : 0).toLocaleString() + " folders · " + Number(fileSense.rows.length > 0 ? fileSense.rows[0].files || 0 : 0).toLocaleString() + " files"; color: window.textMuted; font.pixelSize: 13; elide: Text.ElideRight; Layout.fillWidth: true }
                            }
                        }
                    }

                    RowLayout {
                        visible: window.activePage === "Storage Analyzer" && fileSense.rows.length > 0
                        Layout.fillWidth: true
                        Layout.preferredHeight: 34
                        spacing: 6
                        Repeater {
                            model: ["Folder Breakdown", "File Types (Extensions)", "Treemap View"]
                            delegate: Rectangle {
                                required property string modelData
                                required property int index
                                Layout.preferredWidth: index === 0 ? 156 : (index === 1 ? 194 : 148)
                                Layout.preferredHeight: 34
                                radius: 8
                                color: window.storageActiveTab === index ? window.accent : window.panelRaised
                                border.color: window.storageActiveTab === index ? window.accent : window.border
                                RowLayout {
                                    anchors.centerIn: parent
                                    spacing: 7
                                    Text { text: index === 0 ? "🖿" : (index === 1 ? "\uE9D2" : "\uE9D9"); color: window.storageActiveTab === index ? "#101112" : window.textMuted; font.family: index === 0 ? "Segoe UI Emoji" : "Segoe MDL2 Assets"; font.pixelSize: 13 }
                                    Text { text: modelData; color: window.storageActiveTab === index ? "#101112" : window.textMain; font.pixelSize: 12; font.bold: true }
                                }
                                MouseArea {
                                    anchors.fill: parent
                                    cursorShape: Qt.PointingHandCursor
                                    onClicked: {
                                        window.storageActiveTab = index;
                                        if (index === 2 && fileSense.storageRootPath && !window.storageTreemapPath)
                                            window.storageTreemapPath = fileSense.storageRootPath;
                                    }
                                }
                            }
                        }
                        Item { Layout.fillWidth: true }
                    }

                    Rectangle {
                        visible: window.activePage === "Storage Analyzer" && fileSense.rows.length > 0
                        Layout.fillWidth: true
                        Layout.preferredHeight: Math.max(340, contentScroll.height - 260)
                        radius: 16
                        color: window.panel
                        border.color: window.border
                        ColumnLayout {
                            anchors.fill: parent
                            anchors.margins: 12
                            spacing: 8
                            RowLayout {
                            Layout.fillWidth: true
                            Layout.fillHeight: true
                            spacing: 12
                            Rectangle {
                                visible: window.storageActiveTab === 0
                                Layout.fillWidth: true
                                Layout.fillHeight: true
                                Layout.preferredWidth: 6
                                radius: 12
                                color: window.panelRaised
                                border.color: window.border
                                ColumnLayout {
                                    anchors.fill: parent
                                    anchors.margins: 13
                                    spacing: 8
                                    RowLayout {
                                        Layout.fillWidth: true
                                    Text { text: "🖿"; color: window.accent; font.family: "Segoe UI Emoji"; font.pixelSize: 16; Layout.alignment: Qt.AlignVCenter }
                                    Text { text: "Folder breakdown"; color: window.textMain; font.pixelSize: 15; font.bold: true; Layout.fillWidth: true }
                                        Loader {
                                            sourceComponent: actionButton
                                            onLoaded: {
                                                item.text = "Delete selected";
                                                item.enabled = Qt.binding(function () { return fileSense.storageHasSelection; });
                                                item.clicked.connect(function () { fileSense.deleteStorageSelection(); });
                                            }
                                        }
                                    }
                                    RowLayout {
                                        Layout.fillWidth: true
                                        Layout.leftMargin: 8
                                        Layout.rightMargin: 9
                                        spacing: 8
                                        Item { Layout.preferredWidth: 18; Layout.preferredHeight: 1 }
                                        Item { Layout.preferredWidth: 18; Layout.preferredHeight: 1 }
                                        Item { Layout.preferredWidth: 15; Layout.preferredHeight: 1 }
                                        SortHeader { text: "Name"; color: window.textMuted; sortScope: "storageFolders"; sortKey: "name"; Layout.fillWidth: true; onSortRequested: window.sortedHeader(sortScope, sortKey, sortKind) }
                                        SortHeader { text: "Size"; color: window.textMuted; sortScope: "storageFolders"; sortKey: "size"; sortKind: "size"; Layout.preferredWidth: 68; horizontalAlignment: Text.AlignRight; onSortRequested: window.sortedHeader(sortScope, sortKey, sortKind) }
                                        SortHeader { text: "Allocated"; color: window.textMuted; sortScope: "storageFolders"; sortKey: "allocated"; sortKind: "size"; Layout.preferredWidth: 74; horizontalAlignment: Text.AlignRight; onSortRequested: window.sortedHeader(sortScope, sortKey, sortKind) }
                                        SortHeader { text: "Files"; color: window.textMuted; sortScope: "storageFolders"; sortKey: "files"; sortKind: "number"; Layout.preferredWidth: 48; horizontalAlignment: Text.AlignRight; onSortRequested: window.sortedHeader(sortScope, sortKey, sortKind) }
                                        SortHeader { text: "Folders"; color: window.textMuted; sortScope: "storageFolders"; sortKey: "folders"; sortKind: "number"; Layout.preferredWidth: 54; horizontalAlignment: Text.AlignRight; onSortRequested: window.sortedHeader(sortScope, sortKey, sortKind) }
                                        SortHeader { text: "% parent"; color: window.textMuted; sortScope: "storageFolders"; sortKey: "share"; sortKind: "number"; Layout.preferredWidth: 72; horizontalAlignment: Text.AlignRight; onSortRequested: window.sortedHeader(sortScope, sortKey, sortKind) }
                                    }
                                    ListView {
                                        id: storageFolderList
                                        Layout.fillWidth: true
                                        Layout.fillHeight: true
                                        model: window.activePage === "Storage Analyzer" ? window.sortedStorageRows(fileSense.rows) : []
                                        clip: true
                                        spacing: 2
                                        delegate: Rectangle {
                                            required property var modelData
                                            width: storageFolderList.width
                                            height: 32
                                            radius: 7
                                            color: modelData.selected ? window.panel : (storageHover.hovered ? window.panelRaised : "transparent")
                                            RowLayout {
                                                anchors.fill: parent
                                                anchors.leftMargin: 8
                                                anchors.rightMargin: 9
                                                spacing: 7
                                                Item {
                                                    Layout.preferredWidth: 18
                                                    Layout.preferredHeight: 18
                                                    CheckBox {
                                                        anchors.centerIn: parent
                                                        width: 16
                                                        height: 16
                                                        visible: !modelData.isRoot
                                                        checked: modelData.selected || false
                                                        onToggled: fileSense.setStorageSelected(modelData.path, checked)
                                                        indicator: Rectangle {
                                                            implicitWidth: 16
                                                            implicitHeight: 16
                                                            radius: 4
                                                            color: parent.checked ? window.accent : window.panel
                                                            border.color: parent.checked ? window.accent : window.textMuted
                                                            Text {
                                                                anchors.centerIn: parent
                                                                text: "✓"
                                                                visible: parent.parent.checked
                                                                color: "#101112"
                                                                font.pixelSize: 11
                                                            }
                                                        }
                                                    }
                                                }
                                                Item {
                                                    Layout.preferredWidth: Math.min(modelData.depth || 0, 12) * 12
                                                    Layout.preferredHeight: 1
                                                }
                                                Item {
                                                    Layout.preferredWidth: 18
                                                    Layout.preferredHeight: 22
                                                    AppButton {
                                                        anchors.fill: parent
                                                        visible: modelData.kind === "folder" && modelData.canExpand
                                                        padding: 0
                                                        background: Rectangle { color: "transparent" }
                                                        contentItem: Text {
                                                            text: "›"
                                                            color: window.textMuted
                                                            font.pixelSize: 14
                                                            font.bold: true
                                                            horizontalAlignment: Text.AlignHCenter
                                                            verticalAlignment: Text.AlignVCenter
                                                            rotation: modelData.expanded ? 90 : 0
                                                        }
                                                        onClicked: fileSense.toggleStorageFolder(modelData.path)
                                                    }
                                                }
                                                Item {
                                                    Layout.preferredWidth: 18
                                                    Layout.preferredHeight: 15
                                                    Text { visible: modelData.kind === "folder"; anchors.centerIn: parent; text: "🖿"; color: window.accent; font.family: "Segoe UI Emoji"; font.pixelSize: 14 }
                                                    Rectangle {
                                                        visible: modelData.kind === "file"
                                                        x: 3; y: 1; width: 9; height: 13
                                                        radius: 1
                                                        color: "transparent"
                                                        border.color: window.textMuted
                                                    }
                                                }
                                                Text {
                                                    text: modelData.name
                                                    color: window.textMain
                                                    font.pixelSize: 12
                                                    elide: Text.ElideRight
                                                    Layout.fillWidth: true
                                                }
                                                Text {
                                                    text: modelData.size || "—"
                                                    color: window.textMuted
                                                    font.pixelSize: 10
                                                    Layout.preferredWidth: 68
                                                    horizontalAlignment: Text.AlignRight
                                                }
                                                Text {
                                                    text: modelData.allocated || "—"
                                                    color: window.textMuted
                                                    font.pixelSize: 10
                                                    Layout.preferredWidth: 74
                                                    horizontalAlignment: Text.AlignRight
                                                }
                                                Text {
                                                    text: Number(modelData.files || 0).toLocaleString()
                                                    color: window.textMuted
                                                    font.pixelSize: 10
                                                    Layout.preferredWidth: 48
                                                    horizontalAlignment: Text.AlignRight
                                                }
                                                Text {
                                                    text: Number(modelData.folders || 0).toLocaleString()
                                                    color: window.textMuted
                                                    font.pixelSize: 10
                                                    Layout.preferredWidth: 54
                                                    horizontalAlignment: Text.AlignRight
                                                }
                                                Rectangle {
                                                    Layout.preferredWidth: 72
                                                    Layout.preferredHeight: 20
                                                    radius: 4
                                                    color: window.panel
                                                    border.color: window.border
                                                    Rectangle {
                                                        width: Math.max(0, (parent.width - 2) * Math.min(100, Number(modelData.share || 0)) / 100)
                                                        height: parent.height - 2
                                                        x: 1; y: 1
                                                        radius: 3
                                                        color: window.accent
                                                    }
                                                    Text {
                                                        anchors.fill: parent
                                                        text: (Number(modelData.share || 0)).toFixed(1) + "%"
                                                        color: window.textMain
                                                        font.pixelSize: 9
                                                        horizontalAlignment: Text.AlignHCenter
                                                        verticalAlignment: Text.AlignVCenter
                                                    }
                                                }
                                            }
                                            HoverHandler {
                                                id: storageHover
                                            }
                                            ToolTip.visible: storageHover.hovered
                                            ToolTip.text: modelData.path || ""
                                            ToolTip.delay: 500
                                        }
                                    }
                                }
                            }
                            Item {
                                Layout.fillWidth: true
                                Layout.fillHeight: true
                                Layout.preferredWidth: window.storageActiveTab === 0 ? 4 : 10
                                Rectangle {
                                    anchors.fill: parent
                                visible: window.storageActiveTab === 0 || window.storageActiveTab === 2
                                    radius: 12
                                    color: window.panelRaised
                                    border.color: window.border
                                    ColumnLayout {
                                        anchors.fill: parent
                                        anchors.margins: 14
                                        spacing: 8
                                        RowLayout {
                                            Layout.fillWidth: true
                                            Text { text: "\uE9D9"; color: window.accent; font.family: "Segoe MDL2 Assets"; font.pixelSize: 16; Layout.alignment: Qt.AlignVCenter }
                                            Text { text: "Treemap View"; color: window.textMain; font.pixelSize: 15; font.bold: true; Layout.fillWidth: true }
                                            Text { text: "Squarified disk usage"; color: window.textMuted; font.pixelSize: 10 }
                                        }
                                        RowLayout {
                                            Layout.fillWidth: true
                                            spacing: 6
                                            ColumnLayout {
                                                Layout.fillWidth: true
                                                Layout.preferredWidth: 130
                                                Layout.minimumWidth: 92
                                                spacing: 3
                                                Text { text: "Sort"; color: window.textMuted; font.pixelSize: 10 }
                                                OrganizerComboBox {
                                                    Layout.fillWidth: true
                                                    Layout.preferredHeight: 30
                                                    model: ["Largest first", "Smallest first", "Name A–Z"]
                                                    currentIndex: window.storageTreemapSort
                                                    onActivated: window.storageTreemapSort = currentIndex
                                                }
                                            }
                                            ColumnLayout {
                                                Layout.fillWidth: true
                                                Layout.preferredWidth: 105
                                                Layout.minimumWidth: 82
                                                spacing: 3
                                                Text { text: "Folder depth"; color: window.textMuted; font.pixelSize: 10 }
                                                OrganizerComboBox {
                                                    Layout.fillWidth: true
                                                    Layout.preferredHeight: 30
                                                    model: ["1 level", "2 levels", "3 levels", "5 levels", "All"]
                                                    currentIndex: [1, 2, 3, 5, 0].indexOf(window.storageTreemapDepthLimit)
                                                    onActivated: window.setStorageTreemapDepthLimit([1, 2, 3, 5, 0][currentIndex])
                                                }
                                            }
                                            ColumnLayout {
                                                Layout.fillWidth: true
                                                Layout.preferredWidth: 130
                                                Layout.minimumWidth: 94
                                                spacing: 3
                                                Text { text: "Display metric"; color: window.textMuted; font.pixelSize: 10 }
                                                OrganizerComboBox {
                                                    Layout.fillWidth: true
                                                    Layout.preferredHeight: 30
                                                    model: ["Size", "File Count", "Allocated Space"]
                                                    currentIndex: window.storageTreemapMetric
                                                    onActivated: window.storageTreemapMetric = currentIndex
                                                }
                                            }
                                        }
                                        Flickable {
                                            id: treemapBreadcrumbFlick
                                            Layout.fillWidth: true
                                            Layout.preferredHeight: 24
                                            contentWidth: treemapBreadcrumbRow.implicitWidth
                                            contentHeight: height
                                            clip: true
                                            Row {
                                                id: treemapBreadcrumbRow
                                                height: parent.height
                                                spacing: 5
                                                Repeater {
                                                    model: window.storageTreemapBreadcrumbs()
                                                    delegate: Row {
                                                        required property var modelData
                                                        required property int index
                                                        height: treemapBreadcrumbRow.height
                                                        spacing: 5
                                                        Text { visible: index > 0; text: "›"; color: window.textMuted; font.pixelSize: 13; anchors.verticalCenter: parent.verticalCenter }
                                                        Text {
                                                            id: breadcrumbLabel
                                                            text: modelData.name
                                                            color: index === window.storageTreemapBreadcrumbs().length - 1 ? window.accent : window.textMuted
                                                            font.pixelSize: 11
                                                            font.bold: index === window.storageTreemapBreadcrumbs().length - 1
                                                            elide: Text.ElideRight
                                                            anchors.verticalCenter: parent.verticalCenter
                                                            MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: window.storageTreemapPath = modelData.path }
                                                        }
                                                    }
                                                }
                                            }
                                        }
                                        Item {
                                            id: storageTreemapArea
                                            Layout.fillWidth: true
                                            Layout.fillHeight: true
                                            Repeater {
                                                model: window.storageTreemapTiles()
                                                delegate: Rectangle {
                                                    required property var modelData
                                                    required property int index
                                                    x: modelData.x * storageTreemapArea.width
                                                    y: modelData.y * storageTreemapArea.height
                                                    width: Math.max(1, modelData.w * storageTreemapArea.width - 3)
                                                    height: Math.max(1, modelData.h * storageTreemapArea.height - 3)
                                                    radius: 0
                                                    color: modelData.kind === "folder" ? ["#2998ec", "#9155f5", "#ec4d9d", "#ff9b25", "#f2c230", "#42bf83"][index % 6] : "#343b45"
                                                    border.color: window.panelRaised
                                                    border.width: 1
                                                    Behavior on x { NumberAnimation { duration: 260; easing.type: Easing.OutCubic } }
                                                    Behavior on y { NumberAnimation { duration: 260; easing.type: Easing.OutCubic } }
                                                    Behavior on width { NumberAnimation { duration: 260; easing.type: Easing.OutCubic } }
                                                    Behavior on height { NumberAnimation { duration: 260; easing.type: Easing.OutCubic } }
                                                    Behavior on color { ColorAnimation { duration: 180 } }
                                                    Behavior on border.color { ColorAnimation { duration: 180 } }
                                                    Column {
                                                        anchors.fill: parent
                                                        anchors.margins: 9
                                                        spacing: 3
                                                        Text { text: modelData.name; color: "#ffffff"; font.pixelSize: 12; font.bold: true; elide: Text.ElideRight; width: parent.width; visible: parent.width > 70 && parent.height > 28 }
                                                        Text { text: modelData.metricText; color: "#d7e1e8"; font.pixelSize: 10; elide: Text.ElideRight; width: parent.width; visible: parent.width > 70 && parent.height > 42 }
                                                    }
                                                    MouseArea {
                                                        anchors.fill: parent
                                                        cursorShape: modelData.kind === "folder" ? Qt.PointingHandCursor : Qt.ArrowCursor
                                                        hoverEnabled: true
                                                        onDoubleClicked: {
                                                            window.enterStorageTreemap(modelData.row);
                                                        }
                                                    }
                                                    HoverHandler { id: treemapHover }
                                                    ToolTip.visible: treemapHover.hovered
                                                    ToolTip.text: modelData.kind === "aggregate" ? modelData.name + "\nContains " + modelData.metricText : modelData.name + "\nSize: " + modelData.size + "\nFile count: " + Number(modelData.fileCount || 0).toLocaleString() + "\nAllocated: " + modelData.allocated + (modelData.path ? "\n" + modelData.path : "")
                                                }
                                            }
                                        EmptyResultsState {
                                            anchors.centerIn: parent
                                            visible: window.storageTreemapTiles().length === 0
                                            title: fileSense.storageDirectoryLoading ? "Loading folder contents…" : "No folder usage to display"
                                            description: fileSense.storageDirectoryLoading ? "Reading this folder for the treemap." : "Choose another folder or scan a different drive."
                                        }
                                        }
                                        Text { text: "Double-click a folder to explore · Hover for details"; color: window.textMuted; font.pixelSize: 10 }
                                    }
                                }
                                Rectangle {
                                    id: storageExtensionPanel
                                    anchors.fill: parent
                                    visible: window.storageActiveTab === 1
                                    radius: 12
                                    color: window.panelRaised
                                    border.color: window.border
                                    ColumnLayout {
                                    anchors.fill: parent
                                    anchors.margins: 13
                                    spacing: 8
                                    RowLayout {
                                        Layout.fillWidth: true
                                        Layout.preferredHeight: 158
                                        Layout.maximumHeight: 158
                                        spacing: 14
                                        ColumnLayout {
                                            Layout.fillWidth: true
                                            Layout.preferredWidth: 1
                                            spacing: 5
                                            RowLayout { spacing: 7; Text { text: "\uE9D2"; color: window.accent; font.family: "Segoe MDL2 Assets"; font.pixelSize: 15 } Text { text: "Space by File Type"; color: window.textMain; font.pixelSize: 14; font.bold: true } }
                                            RowLayout {
                                                Layout.fillWidth: true
                                                Layout.preferredHeight: 132
                                                spacing: 12
                                                Item {
                                            Layout.preferredWidth: 126
                                            Layout.preferredHeight: 126
                                            Canvas {
                                                id: storageTypeDonut
                                                anchors.fill: parent
                                                property var chartColors: ["#2998ec", "#9155f5", "#ec4d9d", "#ff9b25", "#f2c230", "#42bf83", "#737b85"]
                                                onPaint: {
                                                    var ctx = getContext("2d");
                                                    ctx.clearRect(0, 0, width, height);
                                                    var rows = fileSense.extensionRows || [];
                                                    var total = 0;
                                                    for (var j = 0; j < rows.length; ++j) total += Math.max(0, Number(rows[j].share || 0));
                                                    var angle = -Math.PI / 2;
                                                    var cx = width / 2, cy = height / 2, radius = Math.min(width, height) * 0.37;
                                                    if (total <= 0) {
                                                        ctx.beginPath(); ctx.arc(cx, cy, radius, 0, Math.PI * 2);
                                                        ctx.strokeStyle = window.border; ctx.lineWidth = 18; ctx.stroke();
                                                        return;
                                                    }
                                                    for (var i = 0; i < rows.length; ++i) {
                                                        var portion = Math.max(0, Number(rows[i].share || 0)) / total * Math.PI * 2;
                                                        ctx.beginPath(); ctx.arc(cx, cy, radius, angle, angle + portion);
                                                        ctx.strokeStyle = chartColors[i % chartColors.length]; ctx.lineWidth = 18; ctx.stroke();
                                                        angle += portion;
                                                    }
                                                }
                                                Connections {
                                                    target: fileSense
                                                    function onChanged() { storageTypeDonut.requestPaint(); }
                                                }
                                            }
                                            Column {
                                                anchors.centerIn: parent
                                                spacing: 1
                                                Text {
                                                    anchors.horizontalCenter: parent.horizontalCenter
                                                    text: String(fileSense.rows.length > 0 ? ((fileSense.rows[0] || {}).size || "—") : "—")
                                                    color: window.textMain; font.pixelSize: 14; font.bold: true
                                                }
                                                Text {
                                                    anchors.horizontalCenter: parent.horizontalCenter
                                                    text: "Logical size"
                                                    color: window.textMuted; font.pixelSize: 9
                                                }
                                            }
                                        }
                                                ColumnLayout {
                                                    Layout.fillWidth: true
                                                    spacing: 3
                                                    Repeater {
                                                        model: fileSense.extensionRows.slice(0, 5)
                                                        delegate: RowLayout {
                                                            required property var modelData
                                                            required property int index
                                                            Layout.fillWidth: true
                                                            spacing: 6
                                                            Rectangle { Layout.preferredWidth: 8; Layout.preferredHeight: 8; radius: 4; color: storageTypeDonut.chartColors[index % storageTypeDonut.chartColors.length] }
                                                            Text { text: modelData.name; color: window.textMain; font.pixelSize: 10; elide: Text.ElideRight; Layout.fillWidth: true }
                                                            Text { text: Number(modelData.share || 0).toFixed(1) + "%"; color: window.textMuted; font.pixelSize: 9; Layout.preferredWidth: 40; horizontalAlignment: Text.AlignRight }
                                                            Text { text: modelData.allocated || "—"; color: window.textMain; font.pixelSize: 9; Layout.preferredWidth: 54; horizontalAlignment: Text.AlignRight }
                                                        }
                                                    }
                                                }
                                            }
                                        }
                                        Rectangle { Layout.preferredWidth: 1; Layout.preferredHeight: 132; color: window.border }
                                        ColumnLayout {
                                            Layout.fillWidth: true
                                            Layout.preferredWidth: 1
                                            spacing: 5
                                            RowLayout { spacing: 7; Text { text: "\uE9D2"; color: window.accent; font.family: "Segoe MDL2 Assets"; font.pixelSize: 15 } Text { text: "Top Extensions"; color: window.textMain; font.pixelSize: 14; font.bold: true } }
                                            ColumnLayout {
                                                Layout.fillWidth: true
                                                spacing: 5
                                                Repeater {
                                                    model: fileSense.extensionRows.slice(0, 5)
                                                    delegate: RowLayout {
                                                        required property var modelData
                                                        required property int index
                                                        Layout.fillWidth: true
                                                        Layout.preferredHeight: 20
                                                        spacing: 8
                                                        Text { text: modelData.name; color: window.textMain; font.pixelSize: 10; elide: Text.ElideRight; Layout.preferredWidth: 76 }
                                                        Rectangle {
                                                            Layout.fillWidth: true
                                                            Layout.preferredHeight: 14
                                                            radius: 7
                                                            color: window.panel
                                                            Rectangle {
                                                                width: Math.max(4, (parent.width - 2) * Math.min(100, Number(modelData.share || 0)) / 100)
                                                                height: parent.height - 2; x: 1; y: 1; radius: 6
                                                                color: storageTypeDonut.chartColors[index % storageTypeDonut.chartColors.length]
                                                            }
                                                        }
                                                        Text { text: modelData.allocated || "—"; color: window.textMuted; font.pixelSize: 10; Layout.preferredWidth: 54; horizontalAlignment: Text.AlignRight }
                                                    }
                                                }
                                            }
                                        }
                                    }
                                    RowLayout {
                                        Layout.fillWidth: true
                                        spacing: 6
                                        SortHeader { text: "Extension"; color: window.textMuted; sortScope: "storageExtensions"; sortKey: "name"; Layout.preferredWidth: 84; onSortRequested: window.sortedHeader(sortScope, sortKey, sortKind) }
                                        SortHeader { text: "Type"; color: window.textMuted; sortScope: "storageExtensions"; sortKey: "type"; Layout.preferredWidth: 64; onSortRequested: window.sortedHeader(sortScope, sortKey, sortKind) }
                                        SortHeader { text: "Share"; color: window.textMuted; sortScope: "storageExtensions"; sortKey: "share"; sortKind: "number"; Layout.fillWidth: true; onSortRequested: window.sortedHeader(sortScope, sortKey, sortKind) }
                                        SortHeader { text: "Size"; color: window.textMuted; sortScope: "storageExtensions"; sortKey: "size"; sortKind: "size"; Layout.preferredWidth: 58; horizontalAlignment: Text.AlignRight; onSortRequested: window.sortedHeader(sortScope, sortKey, sortKind) }
                                        SortHeader { text: "Allocated"; color: window.textMuted; sortScope: "storageExtensions"; sortKey: "allocated"; sortKind: "size"; Layout.preferredWidth: 62; horizontalAlignment: Text.AlignRight; onSortRequested: window.sortedHeader(sortScope, sortKey, sortKind) }
                                        SortHeader { text: "Files"; color: window.textMuted; sortScope: "storageExtensions"; sortKey: "files"; sortKind: "number"; Layout.preferredWidth: 40; horizontalAlignment: Text.AlignRight; onSortRequested: window.sortedHeader(sortScope, sortKey, sortKind) }
                                    }
                                    ListView {
                                        id: extensionList
                                        Layout.fillWidth: true
                                        Layout.fillHeight: true
                                        model: window.activePage === "Storage Analyzer" ? window.sortedResultRows(fileSense.extensionRows, "storageExtensions") : []
                                        clip: true
                                        spacing: 2
                                        delegate: Rectangle {
                                            required property var modelData
                                            width: extensionList.width
                                            height: 34
                                            radius: 7
                                            color: extensionHover.hovered ? window.panel : "transparent"
                                            RowLayout {
                                                anchors.fill: parent
                                                anchors.leftMargin: 5
                                                anchors.rightMargin: 5
                                                spacing: 6
                                                Text {
                                                    text: modelData.name
                                                    color: window.textMain
                                                    font.pixelSize: 11
                                                    font.bold: true
                                                    elide: Text.ElideRight
                                                    Layout.preferredWidth: 84
                                                }
                                                Text {
                                                    text: modelData.type
                                                    color: window.textMuted
                                                    font.pixelSize: 10
                                                    elide: Text.ElideRight
                                                    Layout.preferredWidth: 64
                                                }
                                                Rectangle {
                                                    Layout.fillWidth: true
                                                    Layout.preferredWidth: 66
                                                    Layout.preferredHeight: 18
                                                    radius: 4
                                                    color: window.panel
                                                    border.color: window.border
                                                    Rectangle {
                                                        x: 1; y: 1
                                                        width: Math.max(0, (parent.width - 2) * Math.min(100, Number(modelData.share || 0)) / 100)
                                                        height: parent.height - 2
                                                        radius: 3
                                                        color: window.accent
                                                    }
                                                    Text {
                                                        anchors.fill: parent
                                                        text: Number(modelData.share || 0).toFixed(1) + "%"
                                                        color: window.textMain
                                                        font.pixelSize: 9
                                                        horizontalAlignment: Text.AlignHCenter
                                                        verticalAlignment: Text.AlignVCenter
                                                    }
                                                }
                                                Text {
                                                    text: modelData.size
                                                    color: window.textMuted
                                                    font.pixelSize: 10
                                                    elide: Text.ElideRight
                                                    Layout.preferredWidth: 58
                                                    horizontalAlignment: Text.AlignRight
                                                }
                                                Text {
                                                    text: modelData.allocated
                                                    color: window.textMuted
                                                    font.pixelSize: 10
                                                    elide: Text.ElideRight
                                                    Layout.preferredWidth: 62
                                                    horizontalAlignment: Text.AlignRight
                                                }
                                                Text {
                                                    text: Number(modelData.files || 0).toLocaleString()
                                                    color: window.textMuted
                                                    font.pixelSize: 10
                                                    Layout.preferredWidth: 40
                                                    horizontalAlignment: Text.AlignRight
                                                }
                                            }
                                            HoverHandler {
                                                id: extensionHover
                                            }
                                        }
                                        EmptyResultsState {
                                            anchors.centerIn: parent
                                            visible: extensionList.count === 0
                                            title: "No file types found"
                                            description: "This scan contains no readable files to summarize."
                                        }
                                    }
                                }
                            }
                            }
                            }
                        }
                    }

                    Rectangle {
                        visible: window.activePage === "Storage Analyzer" && fileSense.rows.length === 0
                        Layout.fillWidth: true
                        Layout.preferredHeight: Math.max(220, contentScroll.height - contentColumn.anchors.topMargin - y - 24)
                        radius: 14
                        color: window.panel
                        border.color: window.border
                        EmptyResultsState {
                            anchors.centerIn: parent
                            title: fileSense.storageScanning ? "Scanning storage…" : "No results yet"
                            description: fileSense.storageScanning ? fileSense.status : "Choose a drive or folder and click Scan storage to view its usage."
                        }
                    }

                    Rectangle {
                        id: junkControlsCard
                        visible: window.activePage === "Junk Cleaner"
                        Layout.fillWidth: true
                        Layout.preferredHeight: 94
                        radius: 14
                        color: window.panel
                        border.color: window.border
                        RowLayout {
                            anchors.fill: parent
                            anchors.margins: 14
                            spacing: 16
                            Rectangle {
                                Layout.preferredWidth: 66
                                Layout.preferredHeight: 66
                                radius: 33
                                color: window.panelRaised
                                border.color: window.accent
                                border.width: 3
                                Text {
                                    anchors.centerIn: parent
                                    text: window.iconForPage("Junk Cleaner")
                                    color: window.accent
                                    font.family: "Segoe MDL2 Assets"
                                    font.pixelSize: 28
                                    font.bold: true
                                }
                            }
                            ColumnLayout {
                                Layout.preferredWidth: 150
                                spacing: 2
                                Text {
                                    text: fileSense.junkTotalSizeText
                                    color: window.textMain
                                    font.pixelSize: 24
                                    font.bold: true
                                }
                                Text {
                                    text: "Potential space to free"
                                    color: window.textMuted
                                    font.pixelSize: 11
                                }
                            }
                            Rectangle {
                                Layout.preferredWidth: 1
                                Layout.preferredHeight: 54
                                color: window.border
                            }
                            Text {
                                text: "Clean up junk files, cache and temporary data\nto keep your PC fast and clutter-free."
                                color: window.textMuted
                                font.pixelSize: 12
                                lineHeight: 1.2
                                Layout.fillWidth: true
                            }
                            AnimatedProgressBar {
                                visible: fileSense.junkBusy
                                Layout.preferredWidth: 96
                                Layout.preferredHeight: 6
                                running: visible
                            }
                            Loader {
                                enabled: !fileSense.junkBusy
                                sourceComponent: actionButton
                                onLoaded: {
                                    item.iconText = "\uE72C";
                                    item.text = Qt.binding(function () { return fileSense.categories.length > 0 ? "Rescan" : "Scan cleanup"; });
                                    item.enabled = Qt.binding(function () { return !fileSense.junkBusy; });
                                    item.clicked.connect(fileSense.scanJunk);
                                }
                            }
                            Loader {
                                enabled: !fileSense.junkBusy && fileSense.junkSelectionCount > 0
                                sourceComponent: actionButton
                                onLoaded: {
                                    item.iconText = "\uE74D";
                                    item.text = "Clean Selected";
                                    item.enabled = Qt.binding(function () { return !fileSense.junkBusy && fileSense.junkSelectionCount > 0; });
                                    item.clicked.connect(function () {
                                        fileSense.cleanSelected();
                                    });
                                }
                            }
                        }
                    }

                    Rectangle {
                        id: junkCategoriesCard
                        visible: window.activePage === "Junk Cleaner"
                        Layout.fillWidth: true
                        Layout.preferredHeight: Math.max(360, contentScroll.height - contentColumn.anchors.topMargin - y - 24)
                        radius: 14
                        color: window.panel
                        border.color: window.border
                        ColumnLayout {
                            anchors.fill: parent
                            anchors.margins: 12
                            spacing: 6
                            RowLayout {
                                Layout.fillWidth: true
                                Text { text: "\uE8FD"; color: window.accent; font.family: "Segoe MDL2 Assets"; font.pixelSize: 16; Layout.alignment: Qt.AlignVCenter }
                                Text {
                                    text: "Cleanup results"
                                    color: window.textMain
                                    font.pixelSize: 15
                                    font.bold: true
                                }
                                CheckBox {
                                    id: junkSelectAll
                                    visible: fileSense.junkCandidateCount > 0
                                    enabled: !fileSense.junkBusy
                                    text: "Select all"
                                    checked: fileSense.junkCandidateCount > 0 && fileSense.junkSelectionCount === fileSense.junkCandidateCount
                                    spacing: 6
                                    padding: 0
                                    leftPadding: 24
                                    rightPadding: 0
                                    implicitHeight: 24
                                    Layout.alignment: Qt.AlignVCenter
                                    contentItem: Text {
                                        text: junkSelectAll.text
                                        color: window.textMuted
                                        font.pixelSize: 11
                                        verticalAlignment: Text.AlignVCenter
                                    }
                                    indicator: Rectangle {
                                        x: 0
                                        y: (junkSelectAll.height - height) / 2
                                        implicitWidth: 18
                                        implicitHeight: 18
                                        radius: 3
                                        color: junkSelectAll.checked ? window.accent : window.panelRaised
                                        border.width: junkSelectAll.checked ? 1 : 1.5
                                        border.color: junkSelectAll.checked ? window.accent : (window.lightAppearance ? "#72777b" : "#899398")
                                        Text {
                                            anchors.centerIn: parent
                                            text: "✓"
                                            visible: junkSelectAll.checked
                                            color: "#102321"
                                            font.pixelSize: 11
                                            font.bold: true
                                        }
                                    }
                                    onToggled: window.updateJunkSelection(function () { fileSense.selectAllJunk(junkSelectAll.checked); })
                                }
                                Item { Layout.fillWidth: true }
                                Loader {
                                    visible: fileSense.junkCurrentCategory !== "" && fileSense.junkPageCount > 1
                                    sourceComponent: actionButton
                                    onLoaded: {
                                        item.text = "‹";
                                        item.enabled = Qt.binding(function () { return fileSense.junkPage > 0 && !fileSense.junkBusy; });
                                        item.clicked.connect(function () { fileSense.setJunkPage(fileSense.junkPage - 1); });
                                    }
                                }
                                Text {
                                    visible: fileSense.junkCurrentCategory !== "" && fileSense.junkPageCount > 1
                                    text: (fileSense.junkPage + 1) + " / " + fileSense.junkPageCount
                                    color: window.textMuted
                                    font.pixelSize: 11
                                }
                                Loader {
                                    visible: fileSense.junkCurrentCategory !== "" && fileSense.junkPageCount > 1
                                    sourceComponent: actionButton
                                    onLoaded: {
                                        item.text = "›";
                                        item.enabled = Qt.binding(function () { return fileSense.junkPage + 1 < fileSense.junkPageCount && !fileSense.junkBusy; });
                                        item.clicked.connect(function () { fileSense.setJunkPage(fileSense.junkPage + 1); });
                                    }
                                }
                                Text {
                                    text: fileSense.junkBusy
                                          ? fileSense.status
                                          : fileSense.categories.length > 0
                                            ? "Found " + fileSense.junkTotalSizeText + " cleanup candidates · " + fileSense.categories.length + " categories"
                                            : "Scan to inspect cleanup candidates"
                                    color: window.textMuted
                                    font.pixelSize: 11
                                    elide: Text.ElideRight
                                    horizontalAlignment: Text.AlignRight
                                    Layout.fillWidth: true
                                    Layout.maximumWidth: 620
                                    Layout.alignment: Qt.AlignVCenter
                                }
                            }
                            Rectangle {
                                Layout.fillWidth: true
                                Layout.preferredHeight: 32
                                color: window.panelRaised
                                RowLayout {
                                    anchors.fill: parent
                                    anchors.leftMargin: 8
                                    anchors.rightMargin: 12
                                    spacing: 10
                                    Item { Layout.preferredWidth: 14 }
                                    Item { Layout.preferredWidth: 20 }
                                    Item { Layout.preferredWidth: 28 }
                                    SortHeader { text: "Category / item"; color: window.textMuted; sortScope: "junkItems"; sortKey: "name"; Layout.fillWidth: true; onSortRequested: window.requestJunkSort("name", "name", "text", "text") }
                                    SortHeader { text: "Size"; color: window.textMuted; sortScope: "junkItems"; sortKey: "size"; sortKind: "size"; Layout.preferredWidth: 100; horizontalAlignment: Text.AlignRight; onSortRequested: window.requestJunkSort("size", "size", "size", "size") }
                                    SortHeader { text: "Last modified"; color: window.textMuted; sortScope: "junkItems"; sortKey: "modified"; sortKind: "date"; Layout.preferredWidth: 145; onSortRequested: window.requestJunkSort("modified", "", "date", "text") }
                                    SortHeader { text: "Status"; color: window.textMuted; sortScope: "junkItems"; sortKey: "itemStatus"; Layout.preferredWidth: 145; onSortRequested: window.requestJunkSort("itemStatus", "selectedSize", "text", "number") }
                                }
                            }
                            ListView {
                                id: junkCategoryList
                                Layout.fillWidth: true
                                Layout.fillHeight: true
                                clip: true
                                model: window.sortedJunkCategories()
                                spacing: 1
                                ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }
                                delegate: Item {
                                    required property var modelData
                                    required property int index
                                    width: junkCategoryList.width
                                    property bool startsGroup: modelData.startsGroup === true
                                    property int groupHeaderHeight: startsGroup ? 25 : 0
                                    height: groupHeaderHeight + 36 + (modelData.expanded === true ? Math.max(32, fileSense.rows.length * 34) : 0)
                                    Text {
                                        visible: startsGroup
                                        x: 30
                                        y: 2
                                        width: parent.width - 40
                                        height: 20
                                        text: modelData.group || "Other system items"
                                        color: window.accent
                                        font.pixelSize: 12
                                        font.bold: true
                                        verticalAlignment: Text.AlignVCenter
                                    }
                                    CheckBox {
                                        visible: startsGroup
                                        enabled: !fileSense.junkBusy
                                        tristate: true
                                        checkState: window.junkGroupCheckState(modelData.group)
                                        x: 7
                                        y: 2
                                        width: 18
                                        height: 20
                                        padding: 0
                                        indicator: Rectangle {
                                            implicitWidth: 16
                                            implicitHeight: 16
                                            radius: 4
                                            color: parent.checkState === Qt.Checked ? window.accent : window.panelRaised
                                            border.color: parent.checkState === Qt.Unchecked ? "#647076" : window.accent
                                            Text {
                                                anchors.centerIn: parent
                                                text: parent.parent.checkState === Qt.PartiallyChecked ? "−" : "✓"
                                                visible: parent.parent.checkState !== Qt.Unchecked
                                                color: "#17191a"
                                                font.pixelSize: 11
                                                font.bold: true
                                            }
                                        }
                                        onClicked: {
                                            var groupWasFullySelected = window.junkGroupCheckState(modelData.group) === Qt.Checked;
                                            window.updateJunkSelection(function () {
                                                fileSense.setJunkGroupSelected(modelData.group, !groupWasFullySelected);
                                            });
                                        }
                                    }
                                    Rectangle {
                                        id: junkCategoryRow
                                        y: groupHeaderHeight
                                        width: parent.width
                                        height: 36
                                        color: categoryHover.hovered ? window.panelRaised : "transparent"
                                        RowLayout {
                                            z: 2
                                            anchors.fill: parent
                                            anchors.leftMargin: 8
                                            anchors.rightMargin: 12
                                            spacing: 10
                                            Text {
                                                text: "›"
                                                color: window.textMuted
                                                font.pixelSize: 15
                                                font.bold: true
                                                rotation: modelData.expanded === true ? 90 : 0
                                                Layout.preferredWidth: 14
                                                horizontalAlignment: Text.AlignHCenter
                                            }
                                            CheckBox {
                                                enabled: !fileSense.junkBusy
                                                checked: modelData.checked === true
                                                padding: 0
                                                z: 2
                                                Layout.preferredWidth: 20
                                                Layout.preferredHeight: 20
                                                onToggled: window.updateJunkSelection(function () {
                                                    fileSense.setCategorySelected(modelData.key, checked);
                                                })
                                                indicator: Rectangle {
                                                    implicitWidth: 17
                                                    implicitHeight: 17
                                                    radius: 4
                                                    color: parent.checked ? window.accent : window.panelRaised
                                                    border.color: parent.checked ? window.accent : "#647076"
                                                    Text { anchors.centerIn: parent; text: "✓"; visible: parent.parent.checked; color: "#17191a"; font.pixelSize: 11 }
                                                }
                                            }
                                            Rectangle {
                                                Layout.preferredWidth: 26
                                                Layout.preferredHeight: 26
                                                radius: 7
                                                color: "transparent"
                                                Image {
                                                    anchors.fill: parent
                                                    source: "../assets/junk-cleaner-category-icons.png"
                                                    sourceSize: Qt.size(182, 1054)
                                                    sourceClipRect: Qt.rect(66, window.junkCategoryIconCropY(modelData.key), 64, 64)
                                                    fillMode: Image.PreserveAspectFit
                                                    smooth: true
                                                }
                                            }
                                            Text {
                                                text: (modelData.name || "Category") + " · " + (modelData.itemCount || 0) + " item(s) · " + (modelData.issueCount || 0) + " skipped/info"
                                                color: window.textMain
                                                font.pixelSize: 12
                                                elide: Text.ElideRight
                                                Layout.fillWidth: true
                                                MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: fileSense.toggleJunkCategory(modelData.key) }
                                            }
                                            Text { text: modelData.sizeText || "0 B"; color: window.textMuted; font.pixelSize: 11; horizontalAlignment: Text.AlignRight; Layout.preferredWidth: 100 }
                                            Text { text: "—"; color: window.textMuted; font.pixelSize: 11; Layout.preferredWidth: 145 }
                                            Text { text: "Selected: " + (modelData.selectedSizeText || "0 B"); color: window.textMuted; font.pixelSize: 11; Layout.preferredWidth: 145 }
                                        }
                                        HoverHandler { id: categoryHover }
                                        MouseArea {
                                            anchors.left: parent.left
                                            anchors.top: parent.top
                                            width: 40
                                            height: parent.height
                                            z: 1
                                            cursorShape: Qt.PointingHandCursor
                                            onClicked: fileSense.toggleJunkCategory(modelData.key)
                                        }
                                    }
                                    Repeater {
                                        model: modelData.expanded === true ? fileSense.rows : []
                                        delegate: Rectangle {
                                            required property var modelData
                                            required property int index
                                            x: 22
                                            y: groupHeaderHeight + 36 + index * 34
                                            width: junkCategoryList.width - 22
                                            height: 33
                                            color: index % 2 === 0 ? window.panelRaised : window.panel
                                            RowLayout {
                                                z: 2
                                                anchors.fill: parent
                                                anchors.leftMargin: 28
                                                anchors.rightMargin: 12
                                                spacing: 10
                                                CheckBox {
                                                    checked: modelData.selected
                                                    enabled: !fileSense.junkBusy
                                                    padding: 0
                                                    z: 2
                                                    Layout.preferredWidth: 20
                                                    Layout.preferredHeight: 20
                                                    onToggled: window.updateJunkSelection(function () {
                                                        fileSense.setCandidateSelected(modelData.candidateIndex, checked);
                                                    })
                                                    indicator: Rectangle {
                                                        implicitWidth: 17
                                                        implicitHeight: 17
                                                        radius: 4
                                                        color: parent.checked ? window.accent : window.panelRaised
                                                        border.color: parent.checked ? window.accent : "#647076"
                                                        Text { anchors.centerIn: parent; text: "✓"; visible: parent.parent.checked; color: "#17191a"; font.pixelSize: 11 }
                                                    }
                                                }
                                                Text { text: modelData.name; color: window.textMain; font.pixelSize: 12; elide: Text.ElideRight; Layout.fillWidth: true }
                                                Text { text: modelData.sizeText; color: window.textMuted; font.pixelSize: 11; horizontalAlignment: Text.AlignRight; Layout.preferredWidth: 100 }
                                                Text { text: modelData.modified; color: window.textMuted; font.pixelSize: 11; Layout.preferredWidth: 145 }
                                                Text { text: modelData.itemStatus; color: window.textMuted; font.pixelSize: 11; Layout.preferredWidth: 145 }
                                            }
                                            MouseArea {
                                                anchors.fill: parent
                                                z: 1
                                                cursorShape: Qt.PointingHandCursor
                                                enabled: !fileSense.junkBusy
                                                onClicked: window.updateJunkSelection(function () {
                                                    fileSense.setCandidateSelected(modelData.candidateIndex, !modelData.selected);
                                                })
                                            }
                                        }
                                    }
                                    RowLayout {
                                        visible: modelData.expanded === true && fileSense.rows.length === 0
                                        x: 58
                                        y: 48
                                        spacing: 6
                                        Text { text: "\uE721"; color: window.accent; font.family: "Segoe MDL2 Assets"; font.pixelSize: 13 }
                                        Text { text: "No eligible items found in this category."; color: window.textMuted; font.pixelSize: 11 }
                                    }
                                }
                                Text {
                                    visible: fileSense.categories.length === 0 && fileSense.junkBusy
                                    anchors.centerIn: parent
                                    text: fileSense.status
                                    color: window.textMuted
                                    font.pixelSize: 12
                                    horizontalAlignment: Text.AlignHCenter
                                }
                                EmptyResultsState {
                                    visible: fileSense.categories.length === 0 && !fileSense.junkBusy
                                    anchors.centerIn: parent
                                    title: "No results yet"
                                    description: "Click Scan cleanup to inspect the configured cleanup locations."
                                }
                            }
                        }
                    }

                    Rectangle {
                        id: startupSourcesCard
                        visible: window.activePage === "Startup Manager"
                        Layout.fillWidth: true
                        Layout.preferredHeight: 88
                        radius: 14
                        color: window.panel
                        border.color: window.border
                        RowLayout {
                            anchors.fill: parent
                            anchors.margins: 10
                            spacing: window.width < 1200 ? 12 : 18
                            Rectangle {
                                Layout.preferredWidth: 48
                                Layout.preferredHeight: 48
                                radius: 24
                                color: "#123b58"
                                border.color: "#1689ef"
                                border.width: 2
                                Text {
                                    anchors.centerIn: parent
                                    text: "\uE7E8"
                                    color: "#38a9ff"
                                    font.family: "Segoe MDL2 Assets"
                                    font.pixelSize: 25
                                }
                            }
                            ColumnLayout {
                                spacing: 0
                                Text { text: fileSense.startupAppCount.toLocaleString(); color: window.textMain; font.pixelSize: 22; font.bold: true }
                                Text { text: "Startup Apps"; color: window.textMuted; font.pixelSize: 10 }
                            }
                            Rectangle { Layout.preferredWidth: 1; Layout.preferredHeight: 50; color: window.border }
                            Rectangle {
                                Layout.preferredWidth: 48
                                Layout.preferredHeight: 48
                                radius: 24
                                color: "#163c2a"
                                border.color: "#27d17f"
                                border.width: 2
                                Text { anchors.centerIn: parent; text: "✓"; color: "#27d17f"; font.pixelSize: 22; font.bold: true }
                            }
                            ColumnLayout {
                                spacing: 0
                                Text { text: fileSense.startupAppEnabledCount.toLocaleString(); color: window.textMain; font.pixelSize: 22; font.bold: true }
                                Text { text: "Enabled"; color: window.textMuted; font.pixelSize: 10 }
                            }
                            Rectangle { Layout.preferredWidth: 1; Layout.preferredHeight: 50; color: window.border }
                            Rectangle {
                                Layout.preferredWidth: 48
                                Layout.preferredHeight: 48
                                radius: 24
                                color: "#252c37"
                                border.color: "#77849a"
                                border.width: 2
                                Text {
                                    anchors.centerIn: parent
                                    text: "\uE769"
                                    color: "#aeb9cd"
                                    font.family: "Segoe MDL2 Assets"
                                    font.pixelSize: 19
                                }
                            }
                            ColumnLayout {
                                spacing: 0
                                Text { text: fileSense.startupAppDisabledCount.toLocaleString(); color: window.textMain; font.pixelSize: 22; font.bold: true }
                                Text { text: "Disabled"; color: window.textMuted; font.pixelSize: 10 }
                            }
                            Item { Layout.fillWidth: true }
                            AnimatedProgressBar {
                                visible: fileSense.startupBusy
                                Layout.preferredWidth: window.width < 1200 ? 56 : 86
                                Layout.preferredHeight: 6
                                running: visible
                            }
                            Text {
                                visible: !fileSense.startupBusy && fileSense.startupActionNotice.length === 0
                                         && fileSense.startupAppCount > 0 && window.width > 1220
                                text: fileSense.status
                                color: window.textMuted
                                font.pixelSize: 10
                                elide: Text.ElideRight
                                Layout.maximumWidth: 230
                            }
                            Loader {
                                enabled: !fileSense.startupBusy
                                sourceComponent: actionButton
                                onLoaded: {
                                    item.iconText = "\uE72C";
                                    item.text = "Scan autoruns";
                                    item.enabled = Qt.binding(function () { return !fileSense.startupBusy; });
                                    item.clicked.connect(fileSense.scanStartup);
                                }
                            }
                        }
                    }

                    Rectangle {
                        visible: window.activePage === "File Organizer"
                        Layout.fillWidth: true
                        Layout.preferredHeight: Math.max(420, contentScroll.height - contentColumn.anchors.topMargin - y - 24)
                        Layout.minimumHeight: 380
                        radius: 16
                        color: window.panel
                        border.color: window.border
                        ColumnLayout {
                            anchors.fill: parent
                            anchors.margins: 16
                            spacing: 10
                            RowLayout {
                                Layout.fillWidth: true
                                Item {
                                    id: organizerTabBar
                                    Layout.preferredWidth: 304
                                    Layout.preferredHeight: 38
                                    Item {
                                        id: quickOrganizeTab
                                        x: 0
                                        width: 152
                                        height: 38
                                        y: window.organizerTab === "Quick Organize" ? -1.5 : 0
                                        Behavior on y {
                                            SpringAnimation { spring: 2.0; damping: 0.18; mass: 0.7; epsilon: 0.002 }
                                        }
                                        scale: window.organizerTab === "Quick Organize" ? 1.05 : 1.0
                                        Behavior on scale {
                                            SpringAnimation { spring: 2.0; damping: 0.18; mass: 0.7; epsilon: 0.002 }
                                        }
                                        Shape {
                                            anchors.fill: parent
                                            ShapePath {
                                                strokeWidth: 0
                                                fillColor: window.organizerTab === "Quick Organize" ? window.accent : (quickTabHover.containsMouse ? (window.lightAppearance ? "#dedbd5" : "#303438") : (window.lightAppearance ? "#e9e7e2" : "#222527"))
                                                startX: 0; startY: 0
                                                PathLine { x: 128; y: 0 }
                                                PathLine { x: 152; y: 19 }
                                                PathLine { x: 128; y: 38 }
                                                PathLine { x: 0; y: 38 }
                                                PathLine { x: 0; y: 0 }
                                            }
                                        }
                                        Text {
                                            anchors.centerIn: parent
                                            text: "Quick Organize"
                                            color: window.organizerTab === "Quick Organize" ? "#102321" : window.textMain
                                            font.pixelSize: 14
                                            font.bold: true
                                        }
                                        MouseArea {
                                            id: quickTabHover
                                            anchors.fill: parent
                                            hoverEnabled: true
                                            cursorShape: Qt.PointingHandCursor
                                            onClicked: window.organizerTab = "Quick Organize"
                                        }
                                    }
                                    Item {
                                        id: buildRuleTab
                                        x: 140
                                        width: 164
                                        height: 38
                                        y: window.organizerTab === "Build a Rule" ? -1.5 : 0
                                        Behavior on y {
                                            SpringAnimation { spring: 2.0; damping: 0.18; mass: 0.7; epsilon: 0.002 }
                                        }
                                        scale: window.organizerTab === "Build a Rule" ? 1.05 : 1.0
                                        Behavior on scale {
                                            SpringAnimation { spring: 2.0; damping: 0.18; mass: 0.7; epsilon: 0.002 }
                                        }
                                        Shape {
                                            anchors.fill: parent
                                            ShapePath {
                                                strokeWidth: 0
                                                fillColor: window.organizerTab === "Build a Rule" ? window.accent : (buildTabHover.containsMouse ? (window.lightAppearance ? "#dedbd5" : "#303438") : (window.lightAppearance ? "#e9e7e2" : "#222527"))
                                                startX: 0; startY: 0
                                                PathLine { x: 140; y: 0 }
                                                PathLine { x: 164; y: 19 }
                                                PathLine { x: 140; y: 38 }
                                                PathLine { x: 0; y: 38 }
                                                PathLine { x: 24; y: 19 }
                                                PathLine { x: 0; y: 0 }
                                            }
                                        }
                                        Text {
                                            anchors.centerIn: parent
                                            text: "Build a Rule"
                                            color: window.organizerTab === "Build a Rule" ? "#102321" : window.textMain
                                            font.pixelSize: 14
                                            font.bold: true
                                        }
                                        MouseArea {
                                            id: buildTabHover
                                            anchors.fill: parent
                                            hoverEnabled: true
                                            cursorShape: Qt.PointingHandCursor
                                            onClicked: window.organizerTab = "Build a Rule"
                                        }
                                    }
                                }
                                Item {
                                    Layout.fillWidth: true
                                }
                            }

                            ColumnLayout {
                                visible: window.organizerTab === "Quick Organize"
                                Layout.fillWidth: true
                                Layout.fillHeight: true
                                spacing: 8
                                RowLayout {
                                    Layout.fillWidth: true
                                    spacing: 8
                                    Text { text: "🖿"; color: window.accent; font.family: "Segoe UI Emoji"; font.pixelSize: 16 }
                                    Text { text: "Sort files into categories"; color: window.textMain; font.pixelSize: 15; font.bold: true }
                                }
                                RowLayout {
                                    Layout.fillWidth: true
                                    DarkField {
                                        id: quickSourcePath
                                        Layout.fillWidth: true
                                        placeholderText: "Choose a folder to organize"
                                    }
                                    Loader {
                                        id: quickBrowseButtonLoader
                                        Layout.preferredWidth: 160
                                        sourceComponent: actionButton
                                        onLoaded: {
                                            item.iconText = "🖿";
                                            item.iconFontFamily = "Segoe UI Emoji";
                                            item.text = "Browse folder…";
                                            item.clicked.connect(function () {
                                                folderDialog.target = "quickSource";
                                                folderDialog.open();
                                            });
                                        }
                                    }
                                    CheckBox {
                                        id: quickIncludeSubfolders
                                        text: "Include subfolders"
                                        checked: false
                                        Layout.preferredWidth: 200
                                        leftPadding: 24
                                        contentItem: Text {
                                            text: quickIncludeSubfolders.text
                                            color: window.textMain
                                            font.pixelSize: 13
                                            verticalAlignment: Text.AlignVCenter
                                        }
                                        indicator: Rectangle {
                                            implicitWidth: 16
                                            implicitHeight: 16
                                            x: 0
                                            y: (quickIncludeSubfolders.height - height) / 2
                                            radius: 4
                                            color: quickIncludeSubfolders.checked ? window.accent : window.panelRaised
                                            border.color: quickIncludeSubfolders.checked ? window.accent : window.textMuted
                                            Text {
                                                anchors.centerIn: parent
                                                text: "✓"
                                                visible: quickIncludeSubfolders.checked
                                                color: "#102321"
                                                font.pixelSize: 12
                                            }
                                        }
                                    }
                                }
                                RowLayout {
                                    Layout.fillWidth: true
                                    Item {
                                        id: excludedChipArea
                                        Layout.fillWidth: true
                                        Layout.preferredHeight: quickExcludedFolders.count > 0 ? Math.max(32, quickExcludedFlow.implicitHeight) : 0
                                        Flow {
                                            id: quickExcludedFlow
                                            anchors.left: parent.left
                                            anchors.right: parent.right
                                            anchors.top: parent.top
                                            anchors.leftMargin: 0
                                            visible: quickExcludedFolders.count > 0
                                            spacing: 7
                                            Repeater {
                                                model: quickExcludedFolders
                                                delegate: Rectangle {
                                                    required property string path
                                                    required property int index
                                                    width: Math.min(quickExcludedFlow.width * 0.55, chipPath.implicitWidth + 46)
                                                    height: 32
                                                    radius: 16
                                                    color: window.lightAppearance ? "#efede8" : "#17191b"
                                                    border.color: window.border
                                                    RowLayout {
                                                        anchors.fill: parent
                                                        anchors.leftMargin: 12
                                                        anchors.rightMargin: 5
                                                        spacing: 5
                                                        Text {
                                                            id: chipPath
                                                            text: path
                                                            color: window.textMain
                                                            elide: Text.ElideMiddle
                                                            Layout.fillWidth: true
                                                            ToolTip.visible: chipHover.containsMouse
                                                            ToolTip.text: path
                                                            MouseArea {
                                                                id: chipHover
                                                                anchors.fill: parent
                                                                hoverEnabled: true
                                                            }
                                                        }
                                                        Rectangle {
                                                            width: 21
                                                            height: 21
                                                            radius: 11
                                                            color: chipRemoveHover.containsMouse ? (window.lightAppearance ? "#ddd9d1" : "#292c2e") : "transparent"
                                                            Text {
                                                                anchors.centerIn: parent
                                                                text: "×"
                                                                color: window.textMain
                                                                font.pixelSize: 17
                                                                font.bold: true
                                                            }
                                                            MouseArea {
                                                                id: chipRemoveHover
                                                                anchors.fill: parent
                                                                hoverEnabled: true
                                                                cursorShape: Qt.PointingHandCursor
                                                                onClicked: quickExcludedFolders.remove(index)
                                                            }
                                                            ToolTip.visible: chipRemoveHover.containsMouse
                                                            ToolTip.text: "Remove excluded folder"
                                                        }
                                                    }
                                                }
                                            }
                                        }
                                    }
                                    Loader {
                                        id: quickExcludeButtonLoader
                                        Layout.preferredWidth: 160
                                        Layout.alignment: Qt.AlignTop
                                        sourceComponent: actionButton
                                        onLoaded: {
                                            item.iconText = "\uE738";
                                            item.text = "Exclude folder…";
                                            item.clicked.connect(function () {
                                                folderDialog.target = "quickExclude";
                                                folderDialog.open();
                                            });
                                        }
                                    }
                                    Text {
                                        text: "Excluded Folder (Optional)"
                                        color: window.textMuted
                                        Layout.preferredWidth: 200
                                        Layout.alignment: Qt.AlignTop
                                        Layout.topMargin: 8
                                        horizontalAlignment: Text.AlignLeft
                                        verticalAlignment: Text.AlignVCenter
                                    }
                                }
                                RowLayout {
                                    Layout.fillWidth: true
                                    Layout.topMargin: 8
                                    Loader {
                                        sourceComponent: actionButton
                                        onLoaded: {
                                            item.iconText = "\uE890";
                                            item.text = "Preview";
                                            item.clicked.connect(function () {
                                                fileSense.previewOrganize(quickSourcePath.text, window.excludedFolderPaths().join(";"), quickIncludeSubfolders.checked, quickConflictPolicy.currentText);
                                            });
                                        }
                                    }
                                    Loader {
                                        sourceComponent: actionButton
                                        onLoaded: {
                                            item.iconText = "\uE768";
                                            item.text = "Organize files";
                                            item.clicked.connect(function () {
                                                organizeConfirm.open();
                                            });
                                        }
                                    }
                                    Text {
                                        text: "Default conflict action"
                                        color: window.textMuted
                                        font.pixelSize: 12
                                        verticalAlignment: Text.AlignVCenter
                                    }
                                    OrganizerComboBox {
                                        id: quickConflictPolicy
                                        Layout.preferredWidth: 150
                                        Layout.preferredHeight: 30
                                        model: ["Keep both", "Skip", "Replace"]
                                        currentIndex: 0
                                        onActivated: fileSense.setDefaultCategoryPolicy(currentText)
                                    }
                                    Text {
                                        text: fileSense.status
                                        color: fileSense.status.indexOf("Excluded folders must exist inside the selected source folder") >= 0 ? (window.lightAppearance ? "#a34700" : "#ffb454") : window.textMuted
                                        font.pixelSize: 12
                                        font.bold: fileSense.status.indexOf("Excluded folders must exist inside the selected source folder") >= 0
                                        elide: Text.ElideRight
                                        Layout.maximumWidth: 560
                                    }
                                }
                                Rectangle {
                                    Layout.fillWidth: true
                                    height: 1
                                    color: window.border
                                }
                                RowLayout {
                                    Layout.fillWidth: true
                                    SortHeader { text: "Name"; color: window.textMuted; sortScope: "quickOrganize"; sortKey: "name"; Layout.preferredWidth: 220; onSortRequested: window.sortedHeader(sortScope, sortKey, sortKind) }
                                    SortHeader { text: "Type"; color: window.textMuted; sortScope: "quickOrganize"; sortKey: "type"; Layout.preferredWidth: 120; onSortRequested: window.sortedHeader(sortScope, sortKey, sortKind) }
                                    SortHeader { text: "Size"; color: window.textMuted; sortScope: "quickOrganize"; sortKey: "size"; sortKind: "size"; Layout.preferredWidth: 100; onSortRequested: window.sortedHeader(sortScope, sortKey, sortKind) }
                                    SortHeader { text: "Source Path"; color: window.textMuted; sortScope: "quickOrganize"; sortKey: "path"; Layout.fillWidth: true; onSortRequested: window.sortedHeader(sortScope, sortKey, sortKind) }
                                    SortHeader { text: "Destination Path"; color: window.textMuted; sortScope: "quickOrganize"; sortKey: "destination"; Layout.preferredWidth: 260; onSortRequested: window.sortedHeader(sortScope, sortKey, sortKind) }
                                    SortHeader { text: "Conflict Action"; color: window.textMuted; sortScope: "quickOrganize"; sortKey: "policy"; Layout.preferredWidth: 150; onSortRequested: window.sortedHeader(sortScope, sortKey, sortKind) }
                                }
                                ListView {
                                    id: quickPlanList
                                    Layout.fillWidth: true
                                    Layout.fillHeight: true
                                    Layout.minimumHeight: 90
                                    clip: true
                                    spacing: 2
                                    model: window.activePage === "File Organizer" && window.organizerTab === "Quick Organize" ? window.sortedResultRows(fileSense.quickOrganizeRows, "quickOrganize") : []
                                    delegate: RowLayout {
                                        required property var modelData
                                        required property int index
                                        property int rowIndex: index
                                        width: quickPlanList.width
                                        height: 34
                                        Text {
                                            text: modelData.name || ""
                                            color: window.textMain
                                            elide: Text.ElideRight
                                            Layout.preferredWidth: 220
                                        }
                                        Text {
                                            text: modelData.type || ""
                                            color: window.textMuted
                                            Layout.preferredWidth: 120
                                        }
                                        Text {
                                            text: modelData.size || ""
                                            color: window.textMuted
                                            Layout.preferredWidth: 100
                                        }
                                        Text {
                                            text: modelData.path || ""
                                            color: window.textMuted
                                            elide: Text.ElideMiddle
                                            Layout.fillWidth: true
                                            ToolTip.visible: sourceMouse.containsMouse
                                            ToolTip.text: modelData.path || ""
                                            MouseArea {
                                                id: sourceMouse
                                                anchors.fill: parent
                                                hoverEnabled: true
                                            }
                                        }
                                        Text {
                                            text: modelData.destination || ""
                                            color: window.textMuted
                                            elide: Text.ElideMiddle
                                            Layout.preferredWidth: 260
                                            ToolTip.visible: destMouse.containsMouse
                                            ToolTip.text: modelData.destination || ""
                                            MouseArea {
                                                id: destMouse
                                                anchors.fill: parent
                                                hoverEnabled: true
                                            }
                                        }
                                        OrganizerComboBox {
                                            visible: modelData.conflict === true
                                            Layout.preferredWidth: 150
                                            Layout.preferredHeight: 30
                                            model: ["Keep both", "Skip", "Replace"]
                                            currentIndex: Math.max(0, model.indexOf(modelData.policy))
                                            onActivated: fileSense.setCategoryPolicy(modelData.path, currentText)
                                            contentItem: Text {
                                                leftPadding: 8
                                                text: parent.displayText
                                                color: window.textMain
                                                verticalAlignment: Text.AlignVCenter
                                                elide: Text.ElideRight
                                            }
                                            background: Rectangle {
                                                radius: window.buttonRadius
                                                color: window.panelRaised
                                                border.color: window.border
                                            }
                                        }
                                        Text {
                                            visible: !modelData.conflict
                                            text: ""
                                            color: window.textMuted
                                            Layout.preferredWidth: 150
                                        }
                                    }
                                    EmptyResultsState {
                                        anchors.centerIn: parent
                                        visible: quickPlanList.count === 0
                                        title: "No results yet"
                                        description: "Choose a folder and click Preview to see files to organize."
                                    }
                                }
                            }

                            ColumnLayout {
                                visible: window.organizerTab === "Build a Rule"
                                Layout.fillWidth: true
                                Layout.fillHeight: true
                                spacing: 8
                                RowLayout {
                                    Layout.fillWidth: true
                                    spacing: 8
                                    Text { text: "\uE713"; color: window.accent; font.family: "Segoe MDL2 Assets"; font.pixelSize: 15 }
                                    Text { text: "Build a rule"; color: window.textMain; font.pixelSize: 15; font.bold: true }
                                }
                                Text {
                                    text: "Add monitored folders, then combine conditions from top to bottom."
                                    color: window.textMuted
                                    font.pixelSize: 12
                                }
                                RowLayout {
                                    Layout.fillWidth: true
                                    DarkField {
                                        id: ruleMonitorPaths
                                        Layout.fillWidth: true
                                        placeholderText: "Monitored folder paths (separated by ;)"
                                    }
                                    Loader {
                                        sourceComponent: actionButton
                                        onLoaded: {
                                            item.iconText = "🖿";
                                            item.iconFontFamily = "Segoe UI Emoji";
                                            item.text = "Add folder…";
                                            item.clicked.connect(function () {
                                                folderDialog.target = "monitored";
                                                folderDialog.open();
                                            });
                                        }
                                    }
                                    CheckBox {
                                        id: ruleIncludeSubfolders
                                        text: "Include subfolders"
                                        checked: false
                                        leftPadding: 24
                                        contentItem: Text {
                                            text: ruleIncludeSubfolders.text
                                            color: window.textMain
                                            font.pixelSize: 13
                                            verticalAlignment: Text.AlignVCenter
                                        }
                                        indicator: Rectangle {
                                            implicitWidth: 16
                                            implicitHeight: 16
                                            x: 0
                                            y: (ruleIncludeSubfolders.height - height) / 2
                                            radius: 4
                                            color: ruleIncludeSubfolders.checked ? window.accent : window.panelRaised
                                            border.color: ruleIncludeSubfolders.checked ? window.accent : window.textMuted
                                            Text {
                                                anchors.centerIn: parent
                                                text: "✓"
                                                visible: ruleIncludeSubfolders.checked
                                                color: "#102321"
                                                font.pixelSize: 12
                                            }
                                        }
                                    }
                                }
                                Rectangle {
                                    Layout.fillWidth: true
                                    Layout.preferredHeight: Math.min(230, conditionColumn.implicitHeight + 20)
                                    Layout.minimumHeight: 102
                                    radius: 10
                                    color: window.panelRaised
                                    border.color: window.border
                                    Flickable {
                                        anchors.fill: parent
                                        anchors.margins: 10
                                        contentWidth: width
                                        contentHeight: conditionColumn.implicitHeight
                                        clip: true
                                        ColumnLayout {
                                            id: conditionColumn
                                            width: parent.width
                                            spacing: 6
                                            Repeater {
                                                model: ruleConditions
                                                delegate: RowLayout {
                                                    required property int index
                                                    property int conditionIndex: index
                                                    required property string logic
                                                    required property string field
                                                    required property string operator
                                                    required property string typeValue
                                                    required property string value
                                                    required property string unit
                                                    required property string dateKind
                                                    required property string startDate
                                                    required property string endDate
                                                    required property string period
                                                    required property string periodUnit
                                                    Layout.fillWidth: true
                                                    spacing: 6
                                                    Text {
                                                        visible: conditionIndex === 0
                                                        text: "IF"
                                                        color: window.textMain
                                                        Layout.preferredWidth: 76
                                                        horizontalAlignment: Text.AlignHCenter
                                                    }
                                                    OrganizerComboBox {
                                                        visible: conditionIndex > 0
                                                        Layout.preferredWidth: 76
                                                        Layout.preferredHeight: 30
                                                        model: ["AND", "OR", "NOT"]
                                                        currentIndex: Math.max(0, model.indexOf(logic))
                                                        onActivated: ruleConditions.setProperty(conditionIndex, "logic", currentText)
                                                        contentItem: Text {
                                                            leftPadding: 8
                                                            text: parent.displayText
                                                            color: window.textMain
                                                            verticalAlignment: Text.AlignVCenter
                                                        }
                                                        background: Rectangle {
                                                            radius: window.buttonRadius
                                                            color: window.panel
                                                            border.color: window.border
                                                        }
                                                    }
                                                    OrganizerComboBox {
                                                        id: fieldBox
                                                        Layout.preferredWidth: 150
                                                        Layout.preferredHeight: 30
                                                        model: ["File Type", "File Extension", "File Size", "File Name", "File Date"]
                                                        currentIndex: Math.max(0, model.indexOf(field))
                                                        onActivated: {
                                                            ruleConditions.setProperty(conditionIndex, "field", currentText);
                                                            ruleConditions.setProperty(conditionIndex, "value", "");
                                                            if (currentText === "File Type")
                                                                ruleConditions.setProperty(conditionIndex, "typeValue", "");
                                                            var defaults = {
                                                                "File Type": "Is",
                                                                "File Extension": "Is",
                                                                "File Size": "Is",
                                                                "File Name": "Contains",
                                                                "File Date": "Before"
                                                            };
                                                            ruleConditions.setProperty(conditionIndex, "operator", defaults[currentText]);
                                                        }
                                                        contentItem: Text {
                                                            leftPadding: 8
                                                            text: fieldBox.displayText
                                                            color: window.textMain
                                                            verticalAlignment: Text.AlignVCenter
                                                            elide: Text.ElideRight
                                                        }
                                                        background: Rectangle {
                                                            radius: window.buttonRadius
                                                            color: window.panel
                                                            border.color: window.border
                                                        }
                                                    }
                                                    OrganizerComboBox {
                                                        id: operatorBox
                                                        Layout.preferredWidth: 154
                                                        Layout.preferredHeight: 30
                                                        model: field === "File Type" || field === "File Extension" ? ["Is", "Is not", "Contains", "Does not contain"] : field === "File Size" ? ["Is", "Is not", "Greater than", "Less than", "At least", "At most"] : field === "File Name" ? ["Contains", "Does not contain", "Starts with", "Ends with", "Matches exact text", "Matches pattern (advanced)"] : ["Before", "After", "Between", "Within last", "Older than", "Newer than"]
                                                        currentIndex: Math.max(0, model.indexOf(operator))
                                                        onActivated: ruleConditions.setProperty(conditionIndex, "operator", currentText)
                                                        contentItem: Text {
                                                            leftPadding: 8
                                                            text: operatorBox.displayText
                                                            color: window.textMain
                                                            verticalAlignment: Text.AlignVCenter
                                                            elide: Text.ElideRight
                                                        }
                                                        background: Rectangle {
                                                            radius: window.buttonRadius
                                                            color: window.panel
                                                            border.color: window.border
                                                        }
                                                    }
                                                    OrganizerComboBox {
                                                        visible: field === "File Type"
                                                        Layout.fillWidth: true
                                                        Layout.preferredHeight: 30
                                                        model: ["Compressed", "Video", "Audio", "Images", "Documents", "Programs", "Other"]
                                                        currentIndex: model.indexOf(typeValue)
                                                        onActivated: ruleConditions.setProperty(conditionIndex, "typeValue", currentText)
                                                        contentItem: Text {
                                                            leftPadding: 9
                                                            text: parent.displayText || "Select file type"
                                                            color: window.textMain
                                                            verticalAlignment: Text.AlignVCenter
                                                        }
                                                        background: Rectangle {
                                                            radius: window.buttonRadius
                                                            color: window.panel
                                                            border.color: window.border
                                                        }
                                                    }
                                                    DarkField {
                                                        visible: field === "File Extension" || field === "File Name" || field === "File Size"
                                                        Layout.fillWidth: true
                                                        placeholderText: field === "File Extension" ? "e.g. .jpg or .tar.gz" : field === "File Size" ? "Enter a size" : "Enter a file name or pattern"
                                                        text: value
                                                        onTextEdited: ruleConditions.setProperty(conditionIndex, "value", text)
                                                    }
                                                    OrganizerComboBox {
                                                        visible: field === "File Size"
                                                        Layout.preferredWidth: 66
                                                        Layout.preferredHeight: 30
                                                        model: ["B", "KB", "MB", "GB"]
                                                        currentIndex: Math.max(0, model.indexOf(unit))
                                                        onActivated: ruleConditions.setProperty(conditionIndex, "unit", currentText)
                                                        contentItem: Text {
                                                            leftPadding: 8
                                                            text: parent.displayText
                                                            color: window.textMain
                                                            verticalAlignment: Text.AlignVCenter
                                                        }
                                                        background: Rectangle {
                                                            radius: window.buttonRadius
                                                            color: window.panel
                                                            border.color: window.border
                                                        }
                                                    }
                                                    OrganizerComboBox {
                                                        visible: field === "File Date"
                                                        Layout.preferredWidth: 138
                                                        Layout.preferredHeight: 30
                                                        model: ["Date created", "Date modified", "Date last accessed"]
                                                        currentIndex: Math.max(0, model.indexOf(dateKind))
                                                        onActivated: ruleConditions.setProperty(conditionIndex, "dateKind", currentText)
                                                        contentItem: Text {
                                                            leftPadding: 7
                                                            text: parent.displayText
                                                            color: window.textMain
                                                            verticalAlignment: Text.AlignVCenter
                                                            elide: Text.ElideRight
                                                        }
                                                        background: Rectangle {
                                                            radius: window.buttonRadius
                                                            color: window.panel
                                                            border.color: window.border
                                                        }
                                                    }
                                                    RowLayout {
                                                        id: startRuleDateRow
                                                        property int ruleConditionIndex: conditionIndex
                                                        visible: field === "File Date" && ["Before", "After", "Between"].indexOf(operator) >= 0
                                                        Layout.preferredWidth: 142
                                                        Layout.preferredHeight: 30
                                                        CalendarDateField {
                                                            Layout.fillWidth: true
                                                            Layout.fillHeight: true
                                                            placeholderText: "MM-DD-YYYY"
                                                            text: startDate
                                                            conditionIndex: startRuleDateRow.ruleConditionIndex
                                                            dateProperty: "startDate"
                                                            onTextEdited: ruleConditions.setProperty(startRuleDateRow.ruleConditionIndex, "startDate", value)
                                                        }
                                                    }
                                                    RowLayout {
                                                        id: endRuleDateRow
                                                        property int ruleConditionIndex: conditionIndex
                                                        visible: field === "File Date" && operator === "Between"
                                                        Layout.preferredWidth: 142
                                                        Layout.preferredHeight: 30
                                                        CalendarDateField {
                                                            Layout.fillWidth: true
                                                            Layout.fillHeight: true
                                                            placeholderText: "MM-DD-YYYY"
                                                            text: endDate
                                                            conditionIndex: endRuleDateRow.ruleConditionIndex
                                                            dateProperty: "endDate"
                                                            onTextEdited: ruleConditions.setProperty(endRuleDateRow.ruleConditionIndex, "endDate", value)
                                                        }
                                                    }
                                                    DarkField {
                                                        visible: field === "File Date" && ["Within last", "Older than", "Newer than"].indexOf(operator) >= 0
                                                        Layout.preferredWidth: 56
                                                        placeholderText: "7"
                                                        text: period
                                                        onTextEdited: ruleConditions.setProperty(conditionIndex, "period", text)
                                                    }
                                                    OrganizerComboBox {
                                                        visible: field === "File Date" && ["Within last", "Older than", "Newer than"].indexOf(operator) >= 0
                                                        Layout.preferredWidth: 82
                                                        Layout.preferredHeight: 30
                                                        model: ["Days", "Months", "Years"]
                                                        currentIndex: Math.max(0, model.indexOf(periodUnit))
                                                        onActivated: ruleConditions.setProperty(conditionIndex, "periodUnit", currentText)
                                                        contentItem: Text {
                                                            leftPadding: 8
                                                            text: parent.displayText
                                                            color: window.textMain
                                                            verticalAlignment: Text.AlignVCenter
                                                        }
                                                        background: Rectangle {
                                                            radius: window.buttonRadius
                                                            color: window.panel
                                                            border.color: window.border
                                                        }
                                                    }
                                                    AppButton {
                                                        visible: ruleConditions.count > 1
                                                        Layout.preferredWidth: 30
                                                        Layout.preferredHeight: 30
                                                        text: "×"
                                                        onClicked: ruleConditions.remove(conditionIndex)
                                                        contentItem: Text {
                                                            text: parent.text
                                                            color: window.textMain
                                                            font.pixelSize: 20
                                                            horizontalAlignment: Text.AlignHCenter
                                                            verticalAlignment: Text.AlignVCenter
                                                        }
                                                        background: Rectangle {
                                                            radius: window.buttonRadius
                                                            color: window.panel
                                                            border.color: window.border
                                                        }
                                                    }
                                                }
                                            }
                                            AppButton {
                                                text: "+  Add condition"
                                                implicitHeight: 30
                                                onClicked: ruleConditions.append({
                                                    logic: "AND",
                                                    field: "File Type",
                                                    operator: "Is",
                                                    typeValue: "Images",
                                                    value: "",
                                                    unit: "MB",
                                                    dateKind: "Date modified",
                                                    startDate: "",
                                                    endDate: "",
                                                    period: "7",
                                                    periodUnit: "Days"
                                                })
                                                contentItem: Text {
                                                    text: parent.text
                                                    color: window.textMain
                                                    verticalAlignment: Text.AlignVCenter
                                                    horizontalAlignment: Text.AlignHCenter
                                                }
                                                background: Rectangle {
                                                    radius: window.buttonRadius
                                                    color: window.panel
                                                    border.color: window.border
                                                }
                                            }
                                        }
                                    }
                                }
                                RowLayout {
                                    Layout.fillWidth: true
                                    OrganizerComboBox {
                                        id: ruleAction
                                        Layout.preferredWidth: 130
                                        Layout.preferredHeight: 30
                                        model: ["Move file", "Copy file", "Delete file"]
                                        contentItem: Text {
                                            leftPadding: 9
                                            text: ruleAction.displayText
                                            color: window.textMain
                                            verticalAlignment: Text.AlignVCenter
                                        }
                                        background: Rectangle {
                                            radius: window.buttonRadius
                                            color: window.panelRaised
                                            border.color: window.border
                                        }
                                    }
                                    DarkField {
                                        id: ruleDestination
                                        visible: ruleAction.currentText !== "Delete file"
                                        Layout.fillWidth: true
                                        placeholderText: "Destination folder"
                                    }
                                    Loader {
                                        visible: ruleAction.currentText !== "Delete file"
                                        sourceComponent: actionButton
                                        onLoaded: {
                                            item.iconText = "🖿";
                                            item.iconFontFamily = "Segoe UI Emoji";
                                            item.text = "Browse destination…";
                                            item.clicked.connect(function () {
                                                folderDialog.target = "ruleDestination";
                                                folderDialog.open();
                                            });
                                        }
                                    }
                                    Text {
                                        visible: ruleAction.currentText !== "Delete file"
                                        text: "Default conflict action"
                                        color: window.textMuted
                                        font.pixelSize: 12
                                        verticalAlignment: Text.AlignVCenter
                                    }
                                    OrganizerComboBox {
                                        id: ruleConflictPolicy
                                        visible: ruleAction.currentText !== "Delete file"
                                        Layout.preferredWidth: 130
                                        Layout.preferredHeight: 30
                                        model: ["Keep both", "Skip", "Replace"]
                                        onActivated: fileSense.setDefaultRulePolicy(currentText)
                                        contentItem: Text {
                                            leftPadding: 8
                                            text: ruleConflictPolicy.displayText
                                            color: window.textMain
                                            verticalAlignment: Text.AlignVCenter
                                        }
                                        background: Rectangle {
                                            radius: window.buttonRadius
                                            color: window.panelRaised
                                            border.color: window.border
                                        }
                                    }
                                }
                                RowLayout {
                                    Layout.fillWidth: true
                                    spacing: 8
                                    Loader {
                                        sourceComponent: actionButton
                                        onLoaded: {
                                            item.iconText = "\uE890";
                                            item.text = "Preview";
                                            item.clicked.connect(function () {
                                                if (!window.validateRuleFolders())
                                                    return;
                                                fileSense.previewRule(ruleMonitorPaths.text, ruleIncludeSubfolders.checked, window.collectRuleConditions(), ruleAction.currentText, ruleDestination.text, ruleConflictPolicy.currentText);
                                                if (fileSense.status === "Choose existing monitored source folders.") {
                                                    ruleDestinationDialog.messageText = "Choose existing monitored source folders before previewing or running this rule.";
                                                    ruleDestinationDialog.open();
                                                } else if (fileSense.status === "Choose an existing destination folder.") {
                                                    ruleDestinationDialog.messageText = "Choose an existing destination folder before previewing or running a Move or Copy rule.";
                                                    ruleDestinationDialog.open();
                                                }
                                            });
                                        }
                                    }
                                    Loader {
                                        sourceComponent: actionButton
                                        onLoaded: {
                                            item.iconText = "\uE768";
                                            item.text = "Run rule";
                                            item.clicked.connect(function () {
                                                if (!window.validateRuleFolders())
                                                    return;
                                                fileSense.prepareRuleRun(ruleMonitorPaths.text, ruleIncludeSubfolders.checked, window.collectRuleConditions(), ruleAction.currentText, ruleDestination.text, ruleConflictPolicy.currentText);
                                                if (fileSense.status === "Choose existing monitored source folders.") {
                                                    ruleDestinationDialog.messageText = "Choose existing monitored source folders before previewing or running this rule.";
                                                    ruleDestinationDialog.open();
                                                    return;
                                                }
                                                if (fileSense.status === "Choose an existing destination folder.") {
                                                    ruleDestinationDialog.messageText = "Choose an existing destination folder before previewing or running a Move or Copy rule.";
                                                    ruleDestinationDialog.open();
                                                    return;
                                                }
                                                if (fileSense.ruleRows.length > 0)
                                                    ruleConfirm.open();
                                            });
                                        }
                                    }
                                }
                                RowLayout {
                                    Layout.fillWidth: true
                                    SortHeader { text: "Name"; color: window.textMuted; sortScope: "rule"; sortKey: "name"; Layout.preferredWidth: 200; onSortRequested: window.sortedHeader(sortScope, sortKey, sortKind) }
                                    SortHeader { text: "Type"; color: window.textMuted; sortScope: "rule"; sortKey: "type"; Layout.preferredWidth: 100; onSortRequested: window.sortedHeader(sortScope, sortKey, sortKind) }
                                    SortHeader { text: "Size"; color: window.textMuted; sortScope: "rule"; sortKey: "size"; sortKind: "size"; Layout.preferredWidth: 90; onSortRequested: window.sortedHeader(sortScope, sortKey, sortKind) }
                                    SortHeader { text: "Source Path"; color: window.textMuted; sortScope: "rule"; sortKey: "path"; Layout.fillWidth: true; onSortRequested: window.sortedHeader(sortScope, sortKey, sortKind) }
                                    SortHeader { text: "Destination Path"; color: window.textMuted; sortScope: "rule"; sortKey: "destination"; Layout.preferredWidth: 280; onSortRequested: window.sortedHeader(sortScope, sortKey, sortKind) }
                                    SortHeader { text: "Conflict Action"; color: window.textMuted; sortScope: "rule"; sortKey: "policy"; Layout.preferredWidth: 130; onSortRequested: window.sortedHeader(sortScope, sortKey, sortKind) }
                                }
                                Item {
                                    Layout.fillWidth: true
                                    Layout.fillHeight: true
                                    Layout.minimumHeight: 60
                                    ListView {
                                        id: rulePlanList
                                        anchors.fill: parent
                                        clip: true
                                        spacing: 2
                                        model: window.activePage === "File Organizer" && window.organizerTab === "Build a Rule" ? window.sortedResultRows(fileSense.ruleRows, "rule") : []
                                        delegate: RowLayout {
                                            required property var modelData
                                            required property int index
                                            property int rowIndex: index
                                            width: rulePlanList.width
                                            height: 32
                                            Text {
                                                text: modelData.name
                                                color: window.textMain
                                                elide: Text.ElideRight
                                                Layout.preferredWidth: 200
                                            }
                                            Text {
                                                text: modelData.type || ""
                                                color: window.textMuted
                                                elide: Text.ElideRight
                                                Layout.preferredWidth: 100
                                            }
                                            Text {
                                                text: modelData.size || ""
                                                color: window.textMuted
                                                Layout.preferredWidth: 90
                                            }
                                            Text {
                                                text: modelData.path
                                                color: window.textMuted
                                                elide: Text.ElideMiddle
                                                Layout.fillWidth: true
                                                ToolTip.visible: sourceTip.containsMouse
                                                ToolTip.text: modelData.path || ""
                                                MouseArea {
                                                    id: sourceTip
                                                    anchors.fill: parent
                                                    hoverEnabled: true
                                                }
                                            }
                                            Text {
                                                text: modelData.destination || ""
                                                color: window.textMuted
                                                elide: Text.ElideMiddle
                                                Layout.preferredWidth: 280
                                            }
                                            OrganizerComboBox {
                                                visible: modelData.conflict === true
                                                Layout.preferredWidth: 130
                                                Layout.preferredHeight: 30
                                                model: ["Keep both", "Skip", "Replace"]
                                                currentIndex: Math.max(0, model.indexOf(modelData.policy))
                                                onActivated: fileSense.setRulePolicy(modelData.path, currentText)
                                                contentItem: Text {
                                                    leftPadding: 7
                                                    text: parent.displayText
                                                    color: window.textMain
                                                    verticalAlignment: Text.AlignVCenter
                                                }
                                                background: Rectangle {
                                                    radius: window.buttonRadius
                                                    color: window.panelRaised
                                                    border.color: window.border
                                                }
                                            }
                                            Text {
                                                visible: !modelData.conflict
                                                text: ""
                                                color: window.textMuted
                                                Layout.preferredWidth: 130
                                            }
                                        }
                                    }
                                    EmptyResultsState {
                                        anchors.centerIn: parent
                                        visible: rulePlanList.count === 0
                                        title: fileSense.status === "0 file(s) match the rule." ? "No files match" : "No results yet"
                                        description: fileSense.status === "0 file(s) match the rule."
                                                     ? "Adjust the conditions and preview again."
                                                     : "Click Preview to see files that match the rule."
                                    }
                                }
                            }
                        }
                    }

                    Rectangle {
                        id: duplicateControlsCard
                        visible: window.activePage === "Duplicate Finder"
                        Layout.fillWidth: true
                        Layout.preferredHeight: duplicatePanelContent.implicitHeight + 28
                        radius: 16
                        color: window.panel
                        border.color: window.border
                        ColumnLayout {
                            id: duplicatePanelContent
                            anchors.fill: parent
                            anchors.margins: 14
                            spacing: 8
                            RowLayout {
                                Layout.fillWidth: true
                                Item {
                                    id: duplicateTabBar
                                    Layout.preferredWidth: 320
                                    Layout.preferredHeight: 40
                                    Item {
                                        id: duplicateFindTab
                                        x: 0
                                        width: 160
                                        height: 40
                                        y: duplicateMode === "Find duplicates" ? -1.5 : 0
                                        Behavior on y { SpringAnimation { spring: 2.0; damping: 0.18; mass: 0.7; epsilon: 0.002 } }
                                        scale: duplicateMode === "Find duplicates" ? 1.05 : 1.0
                                        Behavior on scale { SpringAnimation { spring: 2.0; damping: 0.18; mass: 0.7; epsilon: 0.002 } }
                                        Shape {
                                            anchors.fill: parent
                                            ShapePath {
                                                strokeWidth: 0
                                                fillColor: duplicateMode === "Find duplicates" ? window.accent : (duplicateFindHover.containsMouse ? window.panelRaised : (window.lightAppearance ? "#e9e7e2" : "#222527"))
                                                startX: 0; startY: 0
                                                PathLine { x: 136; y: 0 }
                                                PathLine { x: 160; y: 20 }
                                                PathLine { x: 136; y: 40 }
                                                PathLine { x: 0; y: 40 }
                                                PathLine { x: 0; y: 0 }
                                            }
                                        }
                                        Text {
                                            anchors.centerIn: parent
                                            text: "Find duplicates"
                                            color: duplicateMode === "Find duplicates" ? "#102321" : window.textMain
                                            font.pixelSize: 14
                                            font.bold: true
                                        }
                                        MouseArea {
                                            id: duplicateFindHover
                                            anchors.fill: parent
                                            hoverEnabled: true
                                            cursorShape: Qt.PointingHandCursor
                                            onClicked: window.selectDuplicateMode("Find duplicates")
                                        }
                                    }
                                    Item {
                                        id: duplicateRuleTab
                                        x: 148
                                        width: 172
                                        height: 40
                                        y: duplicateMode === "Build a rule" ? -1.5 : 0
                                        Behavior on y { SpringAnimation { spring: 2.0; damping: 0.18; mass: 0.7; epsilon: 0.002 } }
                                        scale: duplicateMode === "Build a rule" ? 1.05 : 1.0
                                        Behavior on scale { SpringAnimation { spring: 2.0; damping: 0.18; mass: 0.7; epsilon: 0.002 } }
                                        Shape {
                                            anchors.fill: parent
                                            ShapePath {
                                                strokeWidth: 0
                                                fillColor: duplicateMode === "Build a rule" ? window.accent : (duplicateRuleHover.containsMouse ? window.panelRaised : (window.lightAppearance ? "#e9e7e2" : "#222527"))
                                                startX: 0; startY: 0
                                                PathLine { x: 148; y: 0 }
                                                PathLine { x: 172; y: 20 }
                                                PathLine { x: 148; y: 40 }
                                                PathLine { x: 0; y: 40 }
                                                PathLine { x: 24; y: 20 }
                                                PathLine { x: 0; y: 0 }
                                            }
                                        }
                                        Text {
                                            anchors.centerIn: parent
                                            text: "Build a rule"
                                            color: duplicateMode === "Build a rule" ? "#102321" : window.textMain
                                            font.pixelSize: 14
                                            font.bold: true
                                        }
                                        MouseArea {
                                            id: duplicateRuleHover
                                            anchors.fill: parent
                                            hoverEnabled: true
                                            cursorShape: Qt.PointingHandCursor
                                            onClicked: window.selectDuplicateMode("Build a rule")
                                        }
                                    }
                                }
                                Item { Layout.fillWidth: true }
                            }
                            RowLayout {
                                Layout.fillWidth: true
                                spacing: 8
                                Text { text: duplicateMode === "Find duplicates" ? "\uE721" : "\uE713"; color: window.accent; font.family: "Segoe MDL2 Assets"; font.pixelSize: 15 }
                                Text { text: duplicateMode === "Find duplicates" ? "Find duplicate files" : "Build a rule"; color: window.textMain; font.pixelSize: 15; font.bold: true }
                            }
                            RowLayout {
                                Layout.fillWidth: true
                                spacing: 8
                                DarkField {
                                    id: duplicateRoot
                                    Layout.fillWidth: true
                                    placeholderText: "Folder paths to scan (separate multiple paths with ;)"
                                }
                                Loader {
                                    Layout.preferredWidth: 160
                                    sourceComponent: actionButton
                                    onLoaded: {
                                        item.iconText = "🖿";
                                        item.iconFontFamily = "Segoe UI Emoji";
                                        item.text = "Browse folder…";
                                        item.clicked.connect(function () {
                                            folderDialog.target = "duplicates";
                                            folderDialog.open();
                                        });
                                    }
                                }
                                CheckBox {
                                    id: duplicateIncludeSubfolders
                                    text: "Include subfolders"
                                    checked: false
                                    Layout.preferredWidth: 200
                                    implicitHeight: 24
                                    implicitWidth: 23 + duplicateIncludeLabel.implicitWidth
                                    padding: 0
                                    leftPadding: 23
                                    rightPadding: 0
                                    contentItem: Text {
                                        id: duplicateIncludeLabel
                                        text: duplicateIncludeSubfolders.text
                                        color: window.textMain
                                        font.pixelSize: 13
                                        verticalAlignment: Text.AlignVCenter
                                    }
                                    indicator: Rectangle {
                                        x: 0
                                        y: (duplicateIncludeSubfolders.height - height) / 2
                                        implicitWidth: 16
                                        implicitHeight: 16
                                        radius: 4
                                        color: duplicateIncludeSubfolders.checked ? window.accent : window.panelRaised
                                        border.color: duplicateIncludeSubfolders.checked ? window.accent : window.textMuted
                                        Text {
                                            anchors.centerIn: parent
                                            text: "✓"
                                            visible: duplicateIncludeSubfolders.checked
                                            color: "#102321"
                                            font.pixelSize: 12
                                        }
                                    }
                                }
                            }
                            RowLayout {
                                Layout.fillWidth: true
                                spacing: 8
                                Flow {
                                    Layout.fillWidth: true
                                    Layout.preferredHeight: duplicateExcludedFolders.count > 0 ? Math.max(32, implicitHeight) : 32
                                    spacing: 7
                                    Repeater {
                                        model: duplicateExcludedFolders
                                        delegate: Rectangle {
                                            required property string path
                                            required property int index
                                            width: Math.min(parent.width * 0.55, duplicateExcludePath.implicitWidth + 46)
                                            height: 32
                                            radius: 16
                                            color: window.lightAppearance ? "#efede8" : "#17191b"
                                            border.color: window.border
                                            RowLayout {
                                                anchors.fill: parent
                                                anchors.leftMargin: 12
                                                anchors.rightMargin: 5
                                                spacing: 5
                                                Text {
                                                    id: duplicateExcludePath
                                                    text: path
                                                    color: window.textMain
                                                    elide: Text.ElideMiddle
                                                    Layout.fillWidth: true
                                                    ToolTip.visible: duplicateExcludeHover.containsMouse
                                                    ToolTip.text: path
                                                    MouseArea {
                                                        id: duplicateExcludeHover
                                                        anchors.fill: parent
                                                        hoverEnabled: true
                                                    }
                                                }
                                                Rectangle {
                                                    width: 21
                                                    height: 21
                                                    radius: 11
                                                    color: duplicateExcludeRemove.containsMouse ? window.panelRaised : "transparent"
                                                    Text {
                                                        anchors.centerIn: parent
                                                        text: "×"
                                                        color: window.textMain
                                                        font.pixelSize: 17
                                                        font.bold: true
                                                    }
                                                    MouseArea {
                                                        id: duplicateExcludeRemove
                                                        anchors.fill: parent
                                                        hoverEnabled: true
                                                        cursorShape: Qt.PointingHandCursor
                                                        onClicked: duplicateExcludedFolders.remove(index)
                                                    }
                                                }
                                            }
                                        }
                                    }
                                }
                                Loader {
                                    Layout.preferredWidth: 160
                                    sourceComponent: actionButton
                                    onLoaded: {
                                        item.iconText = "\uE738";
                                        item.text = "Exclude folder…";
                                        item.clicked.connect(function () {
                                            folderDialog.target = "duplicateExclude";
                                            folderDialog.open();
                                        });
                                    }
                                }
                                Text {
                                    text: "Excluded Folder (Optional)"
                                    color: window.textMuted
                                    font.pixelSize: 12
                                    Layout.preferredWidth: 200
                                    Layout.alignment: Qt.AlignTop
                                    Layout.topMargin: 8
                                    horizontalAlignment: Text.AlignLeft
                                    verticalAlignment: Text.AlignVCenter
                                }
                            }
                            Rectangle {
                                visible: duplicateMode === "Build a rule"
                                Layout.fillWidth: true
                                Layout.preferredHeight: Math.min(230, duplicateConditionColumn.implicitHeight + 20)
                                Layout.minimumHeight: 102
                                radius: 10
                                color: window.panelRaised
                                border.color: window.border
                                Flickable {
                                    anchors.fill: parent
                                    anchors.margins: 10
                                    contentWidth: width
                                    contentHeight: duplicateConditionColumn.implicitHeight
                                    clip: true
                                    ColumnLayout {
                                        id: duplicateConditionColumn
                                        width: parent.width
                                        spacing: 6
                                        Repeater {
                                            model: duplicateConditions
                                            delegate: RowLayout {
                                                required property int index
                                                required property string logic
                                                required property string field
                                                required property string operator
                                                required property string typeValue
                                                required property string value
                                                Layout.fillWidth: true
                                                spacing: 6
                                                Text {
                                                    visible: index === 0
                                                    text: "IF"
                                                    color: window.textMain
                                                    Layout.preferredWidth: 76
                                                    horizontalAlignment: Text.AlignHCenter
                                                    verticalAlignment: Text.AlignVCenter
                                                }
                                                OrganizerComboBox {
                                                    id: duplicateLogic
                                                    visible: index > 0
                                                    Layout.preferredWidth: 76
                                                    Layout.preferredHeight: 30
                                                    model: ["AND", "OR", "NOT"]
                                                    currentIndex: Math.max(0, model.indexOf(logic))
                                                    onActivated: function (choiceIndex) { window.setDuplicateCondition(index, "logic", duplicateLogic.currentText); }
                                                    contentItem: Text {
                                                        leftPadding: 8
                                                        text: duplicateLogic.displayText
                                                        color: window.textMain
                                                        verticalAlignment: Text.AlignVCenter
                                                    }
                                                    background: Rectangle {
                                                        radius: window.buttonRadius
                                                        color: window.panel
                                                        border.color: window.border
                                                    }
                                                }
                                                OrganizerComboBox {
                                                    id: duplicateField
                                                    Layout.preferredWidth: 150
                                                    Layout.preferredHeight: 30
                                                    model: ["File Type", "File Extension"]
                                                    currentIndex: Math.max(0, model.indexOf(field))
                                                    onActivated: function (choiceIndex) {
                                                        window.setDuplicateCondition(index, "field", duplicateField.currentText);
                                                        window.setDuplicateCondition(index, "operator", "Is");
                                                    }
                                                    contentItem: Text {
                                                        leftPadding: 8
                                                        text: duplicateField.displayText
                                                        color: window.textMain
                                                        verticalAlignment: Text.AlignVCenter
                                                        elide: Text.ElideRight
                                                    }
                                                    background: Rectangle {
                                                        radius: window.buttonRadius
                                                        color: window.panel
                                                        border.color: window.border
                                                    }
                                                }
                                                OrganizerComboBox {
                                                    id: duplicateOperator
                                                    Layout.preferredWidth: 154
                                                    Layout.preferredHeight: 30
                                                    model: ["Is", "Is not", "Contains", "Does not contain"]
                                                    currentIndex: Math.max(0, model.indexOf(operator))
                                                    onActivated: function (choiceIndex) { window.setDuplicateCondition(index, "operator", duplicateOperator.currentText); }
                                                    contentItem: Text {
                                                        leftPadding: 8
                                                        text: duplicateOperator.displayText
                                                        color: window.textMain
                                                        verticalAlignment: Text.AlignVCenter
                                                        elide: Text.ElideRight
                                                    }
                                                    background: Rectangle {
                                                        radius: window.buttonRadius
                                                        color: window.panel
                                                        border.color: window.border
                                                    }
                                                }
                                                OrganizerComboBox {
                                                    id: duplicateTypeValue
                                                    visible: field === "File Type"
                                                    Layout.fillWidth: true
                                                    Layout.preferredHeight: 30
                                                    model: ["Compressed", "Video", "Audio", "Images", "Documents", "Programs", "Other"]
                                                    currentIndex: Math.max(0, model.indexOf(typeValue))
                                                    onActivated: function (choiceIndex) { window.setDuplicateCondition(index, "typeValue", duplicateTypeValue.currentText); }
                                                    contentItem: Text {
                                                        leftPadding: 9
                                                        text: duplicateTypeValue.displayText || "Select file type"
                                                        color: window.textMain
                                                        verticalAlignment: Text.AlignVCenter
                                                    }
                                                    background: Rectangle {
                                                        radius: window.buttonRadius
                                                        color: window.panel
                                                        border.color: window.border
                                                    }
                                                }
                                                DarkField {
                                                    visible: duplicateField.currentText === "File Extension"
                                                    Layout.fillWidth: true
                                                    placeholderText: "e.g. .pdf"
                                                    text: value
                                                    onTextEdited: window.setDuplicateCondition(index, "value", text)
                                                }
                                                AppButton {
                                                    visible: duplicateConditions.count > 1
                                                    Layout.preferredWidth: 30
                                                    Layout.preferredHeight: 30
                                                    text: "×"
                                                    onClicked: if (duplicateConditions.count > 1) duplicateConditions.remove(index)
                                                    contentItem: Text {
                                                        text: parent.text
                                                        color: window.textMain
                                                        font.pixelSize: 20
                                                        horizontalAlignment: Text.AlignHCenter
                                                        verticalAlignment: Text.AlignVCenter
                                                    }
                                                    background: Rectangle {
                                                        radius: window.buttonRadius
                                                        color: window.panel
                                                        border.color: window.border
                                                    }
                                                }
                                            }
                                        }
                                        AppButton {
                                            text: "+  Add condition"
                                            implicitHeight: 30
                                            leftPadding: 12
                                            rightPadding: 12
                                            contentItem: Text {
                                                text: parent.text
                                                color: window.textMain
                                                verticalAlignment: Text.AlignVCenter
                                                horizontalAlignment: Text.AlignHCenter
                                            }
                                            background: Rectangle {
                                                radius: window.buttonRadius
                                                color: window.panel
                                                border.color: window.border
                                            }
                                            onClicked: duplicateConditions.append({logic: "AND", field: "File Type", operator: "Is", typeValue: "Images", value: ""})
                                        }
                                    }
                                }
                            }
                            RowLayout {
                                Layout.fillWidth: true
                                Text {
                                    text: "ⓘ  Same-name items are grouped. Checked entries will be sent to the Recycle Bin; unchecked entries will be kept."
                                    color: window.accent
                                    font.pixelSize: 11
                                    Layout.fillWidth: true
                                }
                                Loader {
                                    sourceComponent: actionButton
                                    onLoaded: {
                                        item.iconText = "\uE721";
                                        item.text = "Scan duplicates";
                                        item.clicked.connect(function () {
                                            fileSense.quickScanAt(duplicateRoot.text, "duplicates", duplicateIncludeSubfolders.checked,
                                                                  duplicateMode === "Build a rule" ? collectDuplicateConditions() : [],
                                                                  duplicateExcludedFolderPaths(),
                                                                  duplicateMode === "Build a rule" ? "rule" : "find");
                                        });
                                    }
                                }
                            }
                        }
                    }

                    Rectangle {
                        visible: window.activePage === "About"
                        Layout.fillWidth: true
                        Layout.preferredHeight: 230
                        radius: 16
                        color: window.panel
                        border.color: window.border
                        ColumnLayout {
                            anchors.fill: parent
                            anchors.margins: 24
                            spacing: 8
                            Text {
                                text: "FileSense"
                                color: window.textMain
                                font.pixelSize: 27
                                font.bold: true
                            }
                            Text {
                                text: "One smarter way to manage your PC."
                                color: window.textMain
                                font.pixelSize: 16
                                font.bold: true
                            }
                            Text {
                                text: "Organize files, find duplicates, analyze storage, manage startup items, clean junk files, and search across your folders."
                                color: window.textMuted
                                font.pixelSize: 14
                                wrapMode: Text.WordWrap
                                Layout.fillWidth: true
                            }
                            Item {
                                Layout.preferredHeight: 10
                            }
                            RowLayout {
                                spacing: 4
                                Text {
                                    text: "Crafted by "
                                    color: window.textMain
                                    font.pixelSize: 14
                                }
                                Text {
                                    text: "Ankur"
                                    color: "#ff8a58"
                                    font.pixelSize: 14
                                    font.bold: true
                                }
                                Text {
                                    text: " © Prosoft"
                                    color: window.textMain
                                    font.pixelSize: 14
                                    font.bold: true
                                }
                            }
                            RowLayout {
                                spacing: 6
                                Text {
                                    text: "Follow Me"
                                    color: window.textMain
                                    font.pixelSize: 14
                                    font.bold: true
                                }
                                Item {
                                    width: 20
                                    height: 20
                                    Canvas {
                                        id: instagramIcon
                                        anchors.fill: parent
                                        onPaint: {
                                            var ctx = getContext("2d");
                                            ctx.clearRect(0, 0, width, height);
                                            var gradient = ctx.createLinearGradient(3, 18, 17, 2);
                                            gradient.addColorStop(0, "#ffd776");
                                            gradient.addColorStop(0.48, "#ff4d67");
                                            gradient.addColorStop(1, "#a83bca");
                                            ctx.strokeStyle = gradient;
                                            ctx.fillStyle = gradient;
                                            ctx.lineWidth = 2;
                                            ctx.beginPath();
                                            ctx.moveTo(7, 3);
                                            ctx.lineTo(13, 3);
                                            ctx.quadraticCurveTo(17, 3, 17, 7);
                                            ctx.lineTo(17, 13);
                                            ctx.quadraticCurveTo(17, 17, 13, 17);
                                            ctx.lineTo(7, 17);
                                            ctx.quadraticCurveTo(3, 17, 3, 13);
                                            ctx.lineTo(3, 7);
                                            ctx.quadraticCurveTo(3, 3, 7, 3);
                                            ctx.stroke();
                                            ctx.beginPath();
                                            ctx.arc(10, 10, 3.2, 0, Math.PI * 2);
                                            ctx.stroke();
                                            ctx.beginPath();
                                            ctx.arc(14, 6.2, 1, 0, Math.PI * 2);
                                            ctx.fill();
                                        }
                                    }
                                    MouseArea {
                                        anchors.fill: parent
                                        cursorShape: Qt.PointingHandCursor
                                        onClicked: Qt.openUrlExternally("https://www.instagram.com/ankurtalukdar/")
                                    }
                                }
                                Rectangle {
                                    width: 20
                                    height: 20
                                    radius: 10
                                    color: "#1877F2"
                                    Text {
                                        anchors.fill: parent
                                        text: "f"
                                        color: "white"
                                        font.pixelSize: 16
                                        font.bold: true
                                        horizontalAlignment: Text.AlignHCenter
                                        verticalAlignment: Text.AlignVCenter
                                    }
                                    MouseArea {
                                        anchors.fill: parent
                                        cursorShape: Qt.PointingHandCursor
                                        onClicked: Qt.openUrlExternally("https://www.facebook.com/Ankur4all")
                                    }
                                }
                                Rectangle {
                                    width: 20
                                    height: 20
                                    radius: 4
                                    color: "#0A66C2"
                                    Text {
                                        anchors.fill: parent
                                        text: "in"
                                        color: "white"
                                        font.pixelSize: 11
                                        font.bold: true
                                        horizontalAlignment: Text.AlignHCenter
                                        verticalAlignment: Text.AlignVCenter
                                    }
                                    MouseArea {
                                        anchors.fill: parent
                                        cursorShape: Qt.PointingHandCursor
                                        onClicked: Qt.openUrlExternally("https://www.linkedin.com/in/ankur-talukdar-b9132545/")
                                    }
                                }
                            }
                        }
                    }

                    Rectangle {
                        visible: window.activePage === "Recent Activity"
                        Layout.fillWidth: true
                                Layout.preferredHeight: Math.max(190, Math.min(activityList.contentHeight + 68, contentScroll.height - 72))
                        radius: 16
                        color: window.panel
                        border.color: window.border
                        ColumnLayout {
                            anchors.fill: parent
                            anchors.margins: 16
                            spacing: 10
                            RowLayout {
                                Layout.fillWidth: true
                                spacing: 8
                                Text { text: "\uE81C"; color: window.accent; font.family: "Segoe MDL2 Assets"; font.pixelSize: 16 }
                                Text { text: "Last 30 recorded actions"; color: window.textMain; font.pixelSize: 15; font.bold: true }
                            }
                            RowLayout {
                                Layout.fillWidth: true
                                Layout.leftMargin: 12
                                Layout.rightMargin: 12
                                spacing: 16
                                SortHeader { text: "Date"; color: window.textMuted; sortScope: "activity"; sortKey: "path"; sortKind: "date"; Layout.preferredWidth: 168; onSortRequested: window.sortedHeader(sortScope, sortKey, sortKind) }
                                SortHeader { text: "Action"; color: window.textMuted; sortScope: "activity"; sortKey: "name"; Layout.preferredWidth: 202; onSortRequested: window.sortedHeader(sortScope, sortKey, sortKind) }
                                SortHeader { text: "Details"; color: window.textMuted; sortScope: "activity"; sortKey: "detail"; Layout.fillWidth: true; onSortRequested: window.sortedHeader(sortScope, sortKey, sortKind) }
                            }
                            ListView {
                                id: activityList
                                Layout.fillWidth: true
                                Layout.fillHeight: true
                                model: window.sortedResultRows(fileSense.rows, "activity")
                                clip: true
                                spacing: 3
                                delegate: Rectangle {
                                    required property var modelData
                                    width: activityList.width
                                    height: Math.max(62, activityDetailText.implicitHeight + 42)
                                    radius: 8
                                    color: window.panelRaised
                                    RowLayout {
                                        anchors.fill: parent
                                        anchors.margins: 12
                                        spacing: 16
                                        ColumnLayout {
                                            Layout.preferredWidth: 168
                                            Layout.minimumWidth: 142
                                            Layout.alignment: Qt.AlignVCenter
                                            spacing: 3
                                            Text {
                                                text: {
                                                    var stamp = new Date(modelData.path || "");
                                                    return isNaN(stamp.getTime()) ? "Unknown date" : Qt.formatDate(stamp, "MM-dd-yyyy");
                                                }
                                                color: window.accent
                                                font.pixelSize: 12
                                            }
                                            Text {
                                                text: {
                                                    var stamp = new Date(modelData.path || "");
                                                    return isNaN(stamp.getTime()) ? "" : Qt.formatTime(stamp, "hh:mm AP");
                                                }
                                                color: window.textMuted
                                                font.pixelSize: 11
                                            }
                                        }
                                        Text {
                                            text: modelData.name || ""
                                            color: window.textMain
                                            font.pixelSize: 12
                                            font.bold: true
                                            Layout.preferredWidth: 202
                                            Layout.minimumWidth: 150
                                            Layout.alignment: Qt.AlignVCenter
                                            elide: Text.ElideRight
                                        }
                                        Text {
                                            id: activityDetailText
                                            text: modelData.detail || ""
                                            color: window.textMuted
                                            font.pixelSize: 11
                                            Layout.fillWidth: true
                                            Layout.minimumWidth: 100
                                            Layout.alignment: Qt.AlignVCenter
                                            maximumLineCount: 4
                                            elide: Text.ElideRight
                                            wrapMode: Text.WordWrap
                                        }
                                    }
                                }
                                EmptyResultsState {
                                    anchors.centerIn: parent
                                    visible: activityList.count === 0
                                    title: "No activity yet"
                                    description: "Actions you take in FileSense will appear here."
                                }
                            }
                        }
                    }

                    Rectangle {
                        visible: window.activePage === "Read Me"
                        Layout.fillWidth: true
                        Layout.preferredHeight: Math.max(300, readmeText.implicitHeight + 48)
                        radius: 16
                        color: window.panel
                        border.color: window.border
                        Text {
                            id: readmeText
                            anchors.fill: parent
                            anchors.margins: 22
                            text: fileSense.status
                            textFormat: Text.MarkdownText
                            color: window.textMain
                            font.pixelSize: 13
                            wrapMode: Text.WordWrap
                            linkColor: window.accent
                        }
                    }

                    Rectangle {
                        id: moduleResultsCard
                        visible: window.activePage !== "Home" && window.activePage !== "About" && window.activePage !== "Recent Activity" && window.activePage !== "Read Me" && window.activePage !== "Storage Analyzer" && window.activePage !== "File Organizer" && window.activePage !== "Junk Cleaner"
                        Layout.fillWidth: true
                        Layout.preferredHeight: window.activePage === "File Search & Finder"
                                                ? Math.max(360, resultsViewport.height + 76)
                                                : window.activePage === "Duplicate Finder"
                                                    ? resultsViewport.height + 76
                                                    : window.activePage === "Startup Manager"
                                                        ? resultsViewport.height + 70
                                                    : window.activePage === "Junk Cleaner"
                                                        ? resultsViewport.height + 76
                                                    : contentList.implicitHeight + 68
                        Layout.minimumHeight: 180
                        radius: 16
                        color: window.panel
                        border.color: window.border
                        ColumnLayout {
                            anchors.fill: parent
                            anchors.margins: 16
                            spacing: window.activePage === "Startup Manager" ? 0 : 10
                            RowLayout {
                                visible: window.activePage !== "Startup Manager"
                                Layout.fillWidth: true
                                Layout.preferredHeight: visible ? implicitHeight : 0
                                Layout.minimumHeight: 0
                                Text {
                                    visible: true
                                    text: "\uE8FD"
                                    color: window.accent
                                    font.family: "Segoe MDL2 Assets"
                                    font.pixelSize: 16
                                    Layout.alignment: Qt.AlignVCenter
                                }
                                Text {
                                    text: "Results"
                                    color: window.textMain
                                    font.pixelSize: 15
                                    font.bold: true
                                    Layout.alignment: Qt.AlignVCenter
                                    Layout.leftMargin: 0
                                }
                                CheckBox {
                                    id: searchSelectAll
                                    visible: window.activePage === "File Search & Finder" && fileSense.rows.length > 0
                                    text: "Select all"
                                    checked: fileSense.rows.length > 0 && fileSense.searchSelectionCount === fileSense.rows.length
                                    spacing: 6
                                    padding: 0
                                    implicitHeight: 24
                                    Layout.alignment: Qt.AlignVCenter
                                    leftPadding: 24
                                    rightPadding: 0
                                    contentItem: Text {
                                        text: searchSelectAll.text
                                        color: window.textMuted
                                        font.pixelSize: 11
                                        verticalAlignment: Text.AlignVCenter
                                    }
                                    indicator: Rectangle {
                                        x: 0
                                        y: (searchSelectAll.height - height) / 2
                                        implicitWidth: 18
                                        implicitHeight: 18
                                        radius: 3
                                        color: searchSelectAll.checked ? window.accent : window.panelRaised
                                        border.width: searchSelectAll.checked ? 1 : 1.5
                                        border.color: searchSelectAll.checked ? window.accent : (window.lightAppearance ? "#72777b" : "#899398")
                                        Text {
                                            anchors.centerIn: parent
                                            text: "✓"
                                            visible: searchSelectAll.checked
                                            color: "#102321"
                                            font.pixelSize: 11
                                            font.bold: true
                                        }
                                    }
                                    onToggled: fileSense.selectAllSearchResults(checked)
                                }
                                Text {
                                    visible: window.activePage === "File Search & Finder" && fileSense.searchSelectionCount > 0
                                    text: fileSense.searchSelectionCount + " selected"
                                    color: window.textMuted
                                    font.pixelSize: 11
                                    Layout.alignment: Qt.AlignVCenter
                                }
                                Loader {
                                    visible: window.activePage === "File Search & Finder"
                                    enabled: fileSense.searchSelectionCount > 0
                                    Layout.alignment: Qt.AlignVCenter
                                    sourceComponent: actionButton
                                    onLoaded: {
                                        item.iconText = "\uE8C8";
                                        item.text = "Copy to…";
                                        item.clicked.connect(function () {
                                            folderDialog.target = "searchCopy";
                                            folderDialog.open();
                                        });
                                    }
                                }
                                Loader {
                                    visible: window.activePage === "File Search & Finder"
                                    enabled: fileSense.searchSelectionCount > 0
                                    Layout.alignment: Qt.AlignVCenter
                                    sourceComponent: actionButton
                                    onLoaded: {
                                        item.iconText = "\uE8DE";
                                        item.text = "Move to…";
                                        item.clicked.connect(function () {
                                            folderDialog.target = "searchMove";
                                            folderDialog.open();
                                        });
                                    }
                                }
                                Loader {
                                    visible: window.activePage === "File Search & Finder"
                                    enabled: fileSense.searchSelectionCount > 0
                                    Layout.alignment: Qt.AlignVCenter
                                    sourceComponent: actionButton
                                    onLoaded: {
                                        item.iconText = "\uE74D";
                                        item.text = "Delete";
                                        item.clicked.connect(function () { fileSense.deleteSearchSelection(); });
                                    }
                                }
                                Item {
                                    Layout.fillWidth: true
                                }
                                AnimatedProgressBar {
                                    visible: window.activePage === "File Search & Finder" && fileSense.searchRunning
                                    Layout.preferredWidth: 120
                                    Layout.preferredHeight: 6
                                    running: visible
                                }
                                Text {
                                    text: window.activePage === "Duplicate Finder" ? fileSense.duplicateStatus : fileSense.status
                                    color: window.textMuted
                                    font.pixelSize: 12
                                    elide: Text.ElideRight
                                    Layout.alignment: Qt.AlignVCenter
                                    Layout.maximumWidth: 800
                                }
                                Loader {
                                    visible: window.activePage === "Duplicate Finder"
                                    sourceComponent: actionButton
                                    onLoaded: {
                                        item.text = "Delete";
                                        item.enabled = Qt.binding(function () { return window.duplicateDeleteSelectionCount() > 0; });
                                        item.clicked.connect(function () { duplicateConfirm.open(); });
                                    }
                                }
                            }
                            Rectangle {
                                visible: window.activePage !== "Startup Manager"
                                Layout.fillWidth: true
                                height: visible ? 1 : 0
                                Layout.preferredHeight: height
                                Layout.minimumHeight: 0
                                color: window.border
                            }
                            RowLayout {
                                visible: window.activePage === "Startup Manager"
                                Layout.fillWidth: true
                                Layout.bottomMargin: 8
                                spacing: 10
                                Rectangle {
                                    Layout.preferredWidth: 4
                                    Layout.preferredHeight: 20
                                    radius: 2
                                    color: window.accent
                                }
                                Text { text: "\uE8FD"; color: window.accent; font.family: "Segoe MDL2 Assets"; font.pixelSize: 15; Layout.alignment: Qt.AlignVCenter }
                                Text {
                                    text: window.startupCategoryTitle() + " (" + window.filterStartupRows(fileSense.rows).length.toLocaleString() + ")"
                                    color: window.textMain
                                    font.pixelSize: 14
                                    font.bold: true
                                }
                                OrganizerComboBox {
                                    id: startupCategoryPicker
                                    Layout.preferredWidth: 194
                                    Layout.preferredHeight: 30
                                    model: fileSense.categories
                                    textRole: "label"
                                    currentIndex: {
                                        var cats = fileSense.categories || [];
                                        for (var i = 0; i < cats.length; ++i)
                                            if (cats[i].key === fileSense.startupFilter) return i;
                                        return -1;
                                    }
                                    onActivated: function(index) {
                                        var cats = fileSense.categories || [];
                                        if (index >= 0 && index < cats.length) fileSense.filterStartup(cats[index].key);
                                    }
                                }
                                Item { Layout.fillWidth: true }
                                Item {
                                    Layout.preferredWidth: 230
                                    Layout.preferredHeight: 30
                                    DarkField {
                                        id: startupSearchField
                                        anchors.fill: parent
                                        leftPadding: 32
                                        placeholderText: "Search startup items…"
                                        text: window.startupSearchText
                                        onTextChanged: window.startupSearchText = text
                                    }
                                    Text {
                                        anchors.left: parent.left
                                        anchors.leftMargin: 10
                                        anchors.verticalCenter: parent.verticalCenter
                                        text: "\uE721"
                                        color: window.textMuted
                                        font.family: "Segoe MDL2 Assets"
                                        font.pixelSize: 14
                                    }
                                }
                            }
                            Item {
                                id: resultsViewport
                                property real duplicateNameColumnWidth: Math.max(220, (width - 460) * 0.48)
                                Layout.fillWidth: true
                                Layout.preferredHeight: window.activePage === "File Search & Finder"
                                                        ? Math.max(280, contentScroll.height - searchControlsCard.height - 170)
                                                        : window.activePage === "Duplicate Finder"
                                                            ? Math.max(240, contentScroll.height - duplicateControlsCard.height - 110)
                                                            : window.activePage === "Startup Manager"
                                                                ? Math.max(330, contentScroll.height - startupSourcesCard.height - 180)
                                                            : window.activePage === "Junk Cleaner"
                                                                ? Math.max(240, contentScroll.height - junkControlsCard.height - (fileSense.categories.length > 0 ? junkCategoriesCard.height : 0) - 120)
                                                            : Math.max(76, Math.min(fileSense.rows.length * 56, contentScroll.height - 400))
                                Rectangle {
                                    id: searchTableHeader
                                    visible: window.activePage === "File Search & Finder"
                                    anchors.top: parent.top
                                    anchors.left: parent.left
                                    anchors.right: parent.right
                                    height: 32
                                    color: window.panelRaised
                                    RowLayout {
                                        anchors.fill: parent
                                        anchors.leftMargin: 12
                                        anchors.rightMargin: 12
                                        spacing: 12
                                        Item { Layout.preferredWidth: 18 }
                                        Item { Layout.preferredWidth: 34 }
                                        SortHeader { text: "Name"; color: window.textMuted; sortScope: "search"; sortKey: "name"; Layout.preferredWidth: 220; onSortRequested: window.sortedHeader(sortScope, sortKey, sortKind) }
                                        SortHeader { text: "Type"; color: window.textMuted; sortScope: "search"; sortKey: "type"; Layout.preferredWidth: 110; onSortRequested: window.sortedHeader(sortScope, sortKey, sortKind) }
                                        SortHeader { text: "Size"; color: window.textMuted; sortScope: "search"; sortKey: "size"; sortKind: "size"; Layout.preferredWidth: 90; onSortRequested: window.sortedHeader(sortScope, sortKey, sortKind) }
                                        SortHeader { text: "Date created"; color: window.textMuted; sortScope: "search"; sortKey: "created"; sortKind: "number"; Layout.preferredWidth: 112; onSortRequested: window.sortedHeader(sortScope, sortKey, sortKind) }
                                        SortHeader { text: "Date modified"; color: window.textMuted; sortScope: "search"; sortKey: "modified"; sortKind: "number"; Layout.preferredWidth: 112; onSortRequested: window.sortedHeader(sortScope, sortKey, sortKind) }
                                        SortHeader { text: "Path"; color: window.textMuted; sortScope: "search"; sortKey: "path"; Layout.fillWidth: true; onSortRequested: window.sortedHeader(sortScope, sortKey, sortKind) }
                                    }
                                }
                                ListView {
                                id: contentList
                                anchors.left: parent.left
                                anchors.right: parent.right
                                anchors.bottom: parent.bottom
                                anchors.top: parent.top
                                anchors.topMargin: window.activePage === "Startup Manager" || window.activePage === "File Search & Finder" ? 32 : 0
                                visible: window.activePage !== "Duplicate Finder" && window.activePage !== "Junk Cleaner"
                                model: window.activePage === "Startup Manager" ? window.sortedResultRows(window.filterStartupRows(fileSense.rows), "startup") : window.activePage === "File Search & Finder" ? window.sortedResultRows(fileSense.rows, "search") : fileSense.rows
                                clip: true
                                spacing: 2
                                ScrollBar.vertical: ScrollBar {
                                    policy: ScrollBar.AsNeeded
                                }
                                delegate: Rectangle {
                                    required property var modelData
                                    required property int index
                                    property string startupIconData: window.activePage === "Startup Manager" ? fileSense.startupIcon(modelData.entryId) : ""
                                    width: contentList.width
                                    height: window.activePage === "Startup Manager"
                                            ? 38 + (window.startupAdvancedView && fileSense.selectedStartup.entryId === modelData.entryId ? 128 : 0)
                                            : 54
                                    radius: 8
                                    color: window.activePage === "Startup Manager" && fileSense.selectedStartup.entryId === modelData.entryId
                                           ? Qt.darker(window.accent, 1.45)
                                           : rowHover.containsMouse
                                               ? window.panelRaised
                                           : (window.activePage === "Startup Manager" && index % 2 === 1 ? window.panelRaised : "transparent")
                                    RowLayout {
                                        anchors.left: parent.left
                                        anchors.right: parent.right
                                        anchors.top: parent.top
                                        height: window.activePage === "Startup Manager" ? 38 : parent.height
                                        anchors.leftMargin: 12
                                        anchors.rightMargin: 12
                                        spacing: 12
                                        z: 1
                                        CheckBox {
                                            visible: window.activePage === "File Search & Finder"
                                            Layout.preferredWidth: 18
                                            Layout.preferredHeight: 18
                                            padding: 0
                                            checked: modelData.selected || false
                                            onToggled: fileSense.setSearchResultSelected(modelData.path, checked)
                                            indicator: Rectangle {
                                                x: 0
                                                y: (parent.height - height) / 2
                                                implicitWidth: 16
                                                implicitHeight: 16
                                                radius: 4
                                                color: parent.checked ? window.accent : window.panelRaised
                                                border.color: parent.checked ? window.accent : window.textMuted
                                                Text {
                                                    anchors.centerIn: parent
                                                    text: "✓"
                                                    visible: parent.parent.checked
                                                    color: "#102321"
                                                    font.pixelSize: 10
                                                }
                                            }
                                        }
                                        CheckBox {
                                            visible: window.activePage === "Startup Manager"
                                            Layout.preferredWidth: 18
                                            Layout.preferredHeight: 18
                                            padding: 0
                                            checked: fileSense.selectedStartup.entryId === modelData.entryId
                                            onToggled: checked ? fileSense.selectStartup(modelData.entryId) : fileSense.clearStartupSelection()
                                            indicator: Rectangle {
                                                x: 0
                                                y: (parent.height - height) / 2
                                                implicitWidth: 17
                                                implicitHeight: 17
                                                radius: 4
                                                color: parent.checked ? window.accent : window.panelRaised
                                                border.color: parent.checked ? window.accent : (window.lightAppearance ? "#72777b" : "#899398")
                                                Text { anchors.centerIn: parent; text: "✓"; visible: parent.parent.checked; color: "#102321"; font.pixelSize: 11; font.bold: true }
                                            }
                                        }
                                        CheckBox {
                                            visible: window.activePage === "Duplicate Finder" && modelData.duplicateGroup !== undefined && modelData.duplicateGroup !== ""
                                            checked: modelData.deleteSelected === true
                                            z: 3
                                            onToggled: fileSense.setDuplicateDeleteSelected(modelData.path, checked, duplicateMode === "Build a rule" ? "rule" : "find")
                                            indicator: Rectangle {
                                                implicitWidth: 17
                                                implicitHeight: 17
                                                radius: 5
                                                color: parent.checked ? window.accent : window.panelRaised
                                                border.color: parent.checked ? window.accent : "#647076"
                                                Text {
                                                    anchors.centerIn: parent
                                                    text: "✓"
                                                    visible: parent.parent.checked
                                                    color: "#17191a"
                                                    font.pixelSize: 12
                                                }
                                            }
                                        }
                                        CheckBox {
                                            visible: window.activePage === "Junk Cleaner" && modelData.candidateIndex !== undefined
                                            checked: modelData.selected || false
                                            z: 3
                                            onToggled: window.updateJunkSelection(function () {
                                                fileSense.setCandidateSelected(modelData.candidateIndex, checked);
                                            })
                                            indicator: Rectangle {
                                                implicitWidth: 17
                                                implicitHeight: 17
                                                radius: 5
                                                color: parent.checked ? window.accent : window.panelRaised
                                                border.color: parent.checked ? window.accent : "#647076"
                                                Text {
                                                    anchors.centerIn: parent
                                                    text: "✓"
                                                    visible: parent.parent.checked
                                                    color: "#17191a"
                                                    font.pixelSize: 12
                                                }
                                            }
                                        }
                                        Rectangle {
                                            width: 34
                                            height: 34
                                            radius: 10
                                            color: window.panelRaised
                                            visible: window.activePage !== "Startup Manager"
                                            Text {
                                                anchors.centerIn: parent
                                                text: modelData.path === "Extension" ? "▧" : "•"
                                                color: window.accent
                                                font.pixelSize: 16
                                            }
                                        }
                                        Image {
                                            visible: window.activePage === "Startup Manager" && startupIconData.length > 0
                                            source: startupIconData
                                            sourceSize.width: 28
                                            sourceSize.height: 28
                                            fillMode: Image.PreserveAspectFit
                                            Layout.preferredWidth: 28
                                            Layout.preferredHeight: 28
                                        }
                                        Rectangle {
                                            visible: window.activePage === "Startup Manager" && startupIconData.length === 0
                                            Layout.preferredWidth: 28
                                            Layout.preferredHeight: 28
                                            radius: 6
                                            color: index % 2 === 0 ? "#123d58" : window.panelRaised
                                            Text {
                                                anchors.centerIn: parent
                                                text: String(modelData.name || "?").slice(0, 2).toUpperCase()
                                                color: "#42b7ff"
                                                font.pixelSize: 11
                                                font.bold: true
                                            }
                                        }
                                        ColumnLayout {
                                            spacing: 3
                                            Layout.fillWidth: false
                                            Layout.preferredWidth: window.activePage === "Startup Manager" ? 145 : 220
                                            Text {
                                                text: modelData.name || ""
                                                color: window.textMain
                                                font.pixelSize: window.activePage === "Startup Manager" ? 12 : 13
                                                font.bold: window.activePage === "Startup Manager"
                                                elide: Text.ElideRight
                                                Layout.fillWidth: true
                                            }
                                            Text {
                                                text: modelData.detail || ""
                                                color: window.textMuted
                                                font.pixelSize: 11
                                                elide: Text.ElideRight
                                                Layout.fillWidth: true
                                                visible: window.activePage !== "Startup Manager" && window.activePage !== "File Search & Finder"
                                            }
                                        }
                                        Text {
                                            visible: window.activePage === "File Search & Finder"
                                            text: modelData.type || ""
                                            color: window.textMuted
                                            font.pixelSize: 11
                                            elide: Text.ElideRight
                                            Layout.preferredWidth: 110
                                        }
                                        Text {
                                            visible: window.activePage === "File Search & Finder"
                                            text: modelData.sizeText || ""
                                            color: window.textMuted
                                            font.pixelSize: 11
                                            Layout.preferredWidth: 90
                                        }
                                        Text {
                                            visible: window.activePage === "File Search & Finder"
                                            text: modelData.createdText || "—"
                                            color: window.textMuted
                                            font.pixelSize: 11
                                            Layout.preferredWidth: 112
                                        }
                                        Text {
                                            visible: window.activePage === "File Search & Finder"
                                            text: modelData.modifiedText || "—"
                                            color: window.textMuted
                                            font.pixelSize: 11
                                            Layout.preferredWidth: 112
                                        }
                                        Text {
                                            visible: window.activePage === "Startup Manager"
                                            text: modelData.publisher || "Unknown"
                                            color: window.textMuted
                                            font.pixelSize: 11
                                            elide: Text.ElideRight
                                            Layout.preferredWidth: 172
                                        }
                                        Rectangle {
                                            visible: window.activePage === "Startup Manager"
                                            Layout.preferredWidth: 116
                                            Layout.preferredHeight: 24
                                            radius: 12
                                            color: modelData.status === "Enabled" ? "#102a38" : window.panelRaised
                                            RowLayout {
                                                anchors.fill: parent
                                                anchors.leftMargin: 5
                                                anchors.rightMargin: 8
                                                spacing: 6
                                                Rectangle {
                                                    Layout.preferredWidth: 28
                                                    Layout.preferredHeight: 16
                                                    radius: 8
                                                    color: modelData.status === "Enabled" ? "#149fe8" : "#434a52"
                                                    Rectangle {
                                                        width: 12
                                                        height: 12
                                                        radius: 6
                                                        y: 2
                                                        x: modelData.status === "Enabled" ? 14 : 2
                                                        color: "#f2f5f6"
                                                    }
                                                }
                                                Text {
                                                    text: modelData.status || "Unknown"
                                                    color: modelData.status === "Enabled" ? "#26db85" : (modelData.status === "Disabled" ? "#f06262" : window.textMuted)
                                                    font.pixelSize: 10
                                                    font.bold: true
                                                    Layout.fillWidth: true
                                                }
                                            }
                                            MouseArea {
                                                anchors.fill: parent
                                                z: 3
                                                cursorShape: Qt.PointingHandCursor
                                                onClicked: window.requestStartupAction(modelData)
                                            }
                                        }
                                        Text {
                                            visible: window.activePage === "Startup Manager"
                                            text: modelData.impact || "Unknown"
                                            color: window.textMuted
                                            font.pixelSize: 11
                                            elide: Text.ElideRight
                                            Layout.preferredWidth: 78
                                        }
                                        Text {
                                            visible: window.activePage === "Startup Manager"
                                            text: modelData.duplicate || "No"
                                            color: window.textMuted
                                            font.pixelSize: 11
                                            Layout.preferredWidth: 62
                                        }
                                        Text {
                                            visible: false
                                            text: modelData.executable || "—"
                                            color: window.textMuted
                                            font.pixelSize: 11
                                            elide: Text.ElideMiddle
                                            Layout.fillWidth: true
                                            Layout.preferredWidth: 0
                                        }
                                        Text {
                                            visible: window.activePage === "File Search & Finder" || window.activePage === "Startup Manager"
                                            text: window.activePage === "Startup Manager"
                                                  ? (modelData.executable && modelData.executable !== "—" ? modelData.executable : (modelData.location || "—"))
                                                  : (modelData.destination ? (modelData.path + "  →  " + modelData.destination) : (modelData.source || modelData.path || ""))
                                            color: window.textMuted
                                            font.pixelSize: 11
                                            elide: Text.ElideMiddle
                                            Layout.fillWidth: true
                                            Layout.preferredWidth: window.activePage === "Startup Manager" ? 250 : 0
                                        }
                                        Button {
                                            visible: window.activePage === "Startup Manager"
                                            Layout.preferredWidth: 32
                                            Layout.preferredHeight: 28
                                            text: "▾"
                                            onClicked: {
                                                var wasExpanded = window.startupAdvancedView && fileSense.selectedStartup.entryId === modelData.entryId;
                                                fileSense.selectStartup(modelData.entryId);
                                                window.startupAdvancedView = !wasExpanded;
                                            }
                                            contentItem: Text { text: parent.text; color: window.textMuted; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter; font.pixelSize: 14 }
                                            background: Rectangle { radius: 7; color: parent.down ? window.border : window.panelRaised; border.color: window.border }
                                        }
                                    }
                                    Text {
                                        visible: window.activePage === "Startup Manager" && window.startupAdvancedView && fileSense.selectedStartup.entryId === modelData.entryId
                                        x: 82
                                        y: 42
                                        width: parent.width - 96
                                        height: 120
                                        text: "Publisher: " + (modelData.publisher || "Unknown")
                                              + "\nSource: " + (modelData.source || "Unknown")
                                              + "\nLocation: " + (modelData.location || "—")
                                              + "\nCommand: " + (modelData.command || "—")
                                              + "\nResolved file: " + (modelData.executable || "Unknown")
                                              + "\nArguments: " + (modelData.arguments || "—")
                                        color: window.textMuted
                                        font.pixelSize: 13
                                        wrapMode: Text.WrapAnywhere
                                        elide: Text.ElideRight
                                        z: 2
                                    }
                                    MouseArea {
                                        id: rowHover
                                        anchors.fill: parent
                                        z: 0
                                        hoverEnabled: true
                                        acceptedButtons: Qt.LeftButton | Qt.RightButton
                                        onClicked: if (modelData.entryId)
                                            fileSense.selectStartup(modelData.entryId)
                                        onDoubleClicked: {
                                            if (window.activePage === "Startup Manager") {
                                                if (modelData.executable && modelData.executable !== "—")
                                                    fileSense.openLocation(modelData.executable);
                                            } else {
                                                fileSense.openLocation(modelData.path);
                                            }
                                        }
                                    }
                                }
                                }
                                Rectangle {
                                    id: startupTableHeader
                                    visible: window.activePage === "Startup Manager"
                                    anchors.top: parent.top
                                    anchors.left: parent.left
                                    anchors.right: parent.right
                                    height: 32
                                    color: window.panelRaised
                                    RowLayout {
                                        anchors.fill: parent
                                        anchors.leftMargin: 12
                                        anchors.rightMargin: 12
                                        spacing: 12
                                        Item { Layout.preferredWidth: 18 }
                                        Item { Layout.preferredWidth: 28 }
                                        SortHeader { text: "Name"; color: window.textMuted; sortScope: "startup"; sortKey: "name"; Layout.preferredWidth: 145; onSortRequested: window.sortedHeader(sortScope, sortKey, sortKind) }
                                        SortHeader { text: "Publisher"; color: window.textMuted; sortScope: "startup"; sortKey: "publisher"; Layout.preferredWidth: 172; onSortRequested: window.sortedHeader(sortScope, sortKey, sortKind) }
                                        SortHeader { text: "Status"; color: window.textMuted; sortScope: "startup"; sortKey: "status"; Layout.preferredWidth: 116; onSortRequested: window.sortedHeader(sortScope, sortKey, sortKind) }
                                        SortHeader { text: "Impact"; color: window.textMuted; sortScope: "startup"; sortKey: "impact"; Layout.preferredWidth: 78; onSortRequested: window.sortedHeader(sortScope, sortKey, sortKind) }
                                        SortHeader { text: "Duplicate"; color: window.textMuted; sortScope: "startup"; sortKey: "duplicate"; Layout.preferredWidth: 62; onSortRequested: window.sortedHeader(sortScope, sortKey, sortKind) }
                                        SortHeader { text: "Location"; color: window.textMuted; sortScope: "startup"; sortKey: "location"; Layout.fillWidth: true; onSortRequested: window.sortedHeader(sortScope, sortKey, sortKind) }
                                        Item { Layout.preferredWidth: 32 }
                                    }
                                }
                                ColumnLayout {
                                    anchors.fill: parent
                                    visible: window.activePage === "Duplicate Finder"
                                    spacing: 0
                                    Rectangle {
                                        Layout.fillWidth: true
                                        Layout.preferredHeight: 32
                                        color: window.panelRaised
                                        RowLayout {
                                            anchors.fill: parent
                                            anchors.leftMargin: 10
                                            anchors.rightMargin: 10
                                            spacing: 8
                                            SortHeader { text: "Name / Group"; color: window.textMuted; sortScope: window.duplicateMode === "Build a rule" ? "duplicateRule" : "duplicateFind"; sortKey: "name"; Layout.preferredWidth: resultsViewport.duplicateNameColumnWidth; onSortRequested: window.sortedHeader(sortScope, sortKey, sortKind) }
                                            Text { text: "Delete"; color: window.textMuted; font.pixelSize: 11; horizontalAlignment: Text.AlignHCenter; Layout.preferredWidth: 62 }
                                            SortHeader { text: "Type"; color: window.textMuted; sortScope: window.duplicateMode === "Build a rule" ? "duplicateRule" : "duplicateFind"; sortKey: "fileType"; Layout.preferredWidth: 72; onSortRequested: window.sortedHeader(sortScope, sortKey, sortKind) }
                                            SortHeader { text: "Size"; color: window.textMuted; sortScope: window.duplicateMode === "Build a rule" ? "duplicateRule" : "duplicateFind"; sortKey: "size"; sortKind: "size"; Layout.preferredWidth: 116; onSortRequested: window.sortedHeader(sortScope, sortKey, sortKind) }
                                            SortHeader { text: "Size comparison"; color: window.textMuted; sortScope: window.duplicateMode === "Build a rule" ? "duplicateRule" : "duplicateFind"; sortKey: "sizeComparison"; Layout.preferredWidth: 132; onSortRequested: window.sortedHeader(sortScope, sortKey, sortKind) }
                                            SortHeader { text: "Location"; color: window.textMuted; sortScope: window.duplicateMode === "Build a rule" ? "duplicateRule" : "duplicateFind"; sortKey: "path"; Layout.fillWidth: true; onSortRequested: window.sortedHeader(sortScope, sortKey, sortKind) }
                                        }
                                    }
                                    ListView {
                                        id: duplicateResultsList
                                        Layout.fillWidth: true
                                        Layout.fillHeight: true
                                        model: duplicateResultRows
                                        clip: true
                                        spacing: 0
                                        ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }
                                        delegate: Rectangle {
                                            required property int index
                                            required property string rowKind
                                            required property string groupKey
                                            required property bool expanded
                                            required property string name
                                            required property string fileType
                                            required property string sizeText
                                            required property string sizeComparison
                                            required property string path
                                            required property bool deleteSelected
                                            width: duplicateResultsList.width
                                            height: rowKind === "group" ? 29 : 27
                                            color: rowKind === "group" ? window.panelRaised : (index % 2 === 0 ? window.panel : window.panelRaised)
                                            RowLayout {
                                                anchors.fill: parent
                                                anchors.leftMargin: 10
                                                anchors.rightMargin: 10
                                                spacing: 8
                                                Item {
                                                    Layout.preferredWidth: resultsViewport.duplicateNameColumnWidth
                                                    Layout.fillHeight: true
                                                    RowLayout {
                                                        anchors.fill: parent
                                                        spacing: 5
                                                        Item {
                                                            width: rowKind === "group" ? 19 : 19
                                                            height: 22
                                                            Text {
                                                                anchors.centerIn: parent
                                                                visible: rowKind === "group"
                                                                text: "›"
                                                                width: 18
                                                                height: 18
                                                                horizontalAlignment: Text.AlignHCenter
                                                                verticalAlignment: Text.AlignVCenter
                                                                rotation: expanded ? 90 : 0
                                                                Behavior on rotation { NumberAnimation { duration: 120; easing.type: Easing.OutCubic } }
                                                                color: window.textMain
                                                                font.pixelSize: 15
                                                            }
                                                            MouseArea {
                                                                anchors.fill: parent
                                                                visible: rowKind === "group"
                                                                cursorShape: Qt.PointingHandCursor
                                                                onClicked: window.toggleDuplicateGroup(groupKey)
                                                            }
                                                        }
                                                        Text {
                                                            Layout.fillWidth: true
                                                            text: name
                                                            color: window.textMain
                                                            font.pixelSize: 11
                                                            font.bold: rowKind === "group"
                                                            elide: Text.ElideRight
                                                            verticalAlignment: Text.AlignVCenter
                                                        }
                                                    }
                                                }
                                                Item {
                                                    Layout.preferredWidth: 62
                                                    Layout.fillHeight: true
                                                    CheckBox {
                                                        anchors.centerIn: parent
                                                        visible: rowKind === "entry"
                                                        width: 18
                                                        height: 18
                                                        padding: 0
                                                        checked: deleteSelected
                                                        onToggled: fileSense.setDuplicateDeleteSelected(path, checked, duplicateMode === "Build a rule" ? "rule" : "find")
                                                        indicator: Rectangle {
                                                            implicitWidth: 16
                                                            implicitHeight: 16
                                                            radius: 4
                                                            color: parent.checked ? window.accent : window.panel
                                                            border.color: parent.checked ? window.accent : window.textMuted
                                                            Text {
                                                                anchors.centerIn: parent
                                                                text: "✓"
                                                                visible: parent.parent.checked
                                                                color: "#102321"
                                                                font.pixelSize: 10
                                                            }
                                                        }
                                                    }
                                                }
                                                Text { text: fileType; color: window.textMain; font.pixelSize: 11; Layout.preferredWidth: 72; verticalAlignment: Text.AlignVCenter }
                                                Text { text: sizeText; color: window.textMain; font.pixelSize: 11; Layout.preferredWidth: 116; verticalAlignment: Text.AlignVCenter }
                                                Text { text: sizeComparison; color: window.textMuted; font.pixelSize: 11; Layout.preferredWidth: 132; elide: Text.ElideRight; verticalAlignment: Text.AlignVCenter }
                                                Text {
                                                    text: path
                                                    color: window.textMuted
                                                    font.pixelSize: 11
                                                    Layout.fillWidth: true
                                                    elide: Text.ElideMiddle
                                                    verticalAlignment: Text.AlignVCenter
                                                    MouseArea {
                                                        anchors.fill: parent
                                                        acceptedButtons: Qt.LeftButton
                                                        onDoubleClicked: fileSense.openLocation(path)
                                                    }
                                                }
                                            }
                                        }
                                    }
                                }
                                Text {
                                    visible: (window.activePage === "File Search & Finder" && fileSense.searchRunning)
                                             || (window.activePage === "Startup Manager" && fileSense.startupBusy)
                                             || (window.activePage === "Duplicate Finder" && fileSense.duplicateBusy)
                                    anchors.centerIn: parent
                                    text: window.activePage === "Duplicate Finder" ? fileSense.duplicateStatus : fileSense.status
                                    color: window.textMuted
                                    font.pixelSize: 12
                                    horizontalAlignment: Text.AlignHCenter
                                    verticalAlignment: Text.AlignVCenter
                                }
                                EmptyResultsState {
                                    visible: (window.activePage === "File Search & Finder" && fileSense.rows.length === 0 && !fileSense.searchRunning)
                                             || (window.activePage === "Duplicate Finder" && fileSense.duplicateRows.length === 0 && !fileSense.duplicateBusy)
                                             || (window.activePage === "Startup Manager" && window.filterStartupRows(fileSense.rows).length === 0 && !fileSense.startupBusy)
                                    anchors.centerIn: parent
                                    title: window.activePage === "File Search & Finder"
                                           ? (fileSense.status.indexOf("Found 0") === 0 ? "No files matched" : "No results yet")
                                           : window.activePage === "Duplicate Finder"
                                             ? (fileSense.duplicateStatus.indexOf("Found 0") === 0 ? "No duplicates found" : "No results yet")
                                             : (window.startupSearchText.trim().length > 0 ? "No startup entries match" : "No startup entries yet")
                                    description: window.activePage === "File Search & Finder"
                                                 ? (fileSense.status.indexOf("Found 0") === 0 ? "Try changing the search filters or selected folders." : "Enter search criteria and click Search to find files.")
                                                 : window.activePage === "Duplicate Finder"
                                                   ? (duplicateMode === "Build a rule" ? "Choose folders, add conditions, and scan to find matching duplicate files." : "Choose folders and scan to find duplicate files.")
                                                   : (window.startupSearchText.trim().length > 0 ? "Try another search term." : "Click Scan autoruns to inspect startup entries.")
                                }
                            }
                        }
                    }

                    Rectangle {
                        id: startupDetailsCard
                        visible: false
                        Layout.fillWidth: true
                        Layout.preferredHeight: 204
                        radius: 14
                        color: window.panel
                        border.color: window.border
                        ColumnLayout {
                            anchors.fill: parent
                            anchors.margins: 15
                            spacing: 8
                            RowLayout {
                                Layout.fillWidth: true
                                Text { text: "\uE946"; color: window.accent; font.family: "Segoe MDL2 Assets"; font.pixelSize: 16; Layout.alignment: Qt.AlignVCenter }
                                Text {
                                    text: "Entry details"
                                    color: window.textMain
                                    font.pixelSize: 15
                                    font.bold: true
                                    Layout.fillWidth: true
                                }
                                Text {
                                    text: fileSense.selectedStartup.displayStatus || fileSense.selectedStartup.status || ""
                                    color: window.accent
                                    font.pixelSize: 12
                                    font.bold: true
                                }
                            }
                            Text {
                                id: startupDetailText
                                visible: fileSense.selectedStartup.entryId !== undefined
                                text: "Name: " + (fileSense.selectedStartup.name || "") + "\nSource: " + (fileSense.selectedStartup.source || "") + "\nLocation: " + (fileSense.selectedStartup.location || "") + "\nCommand: " + (fileSense.selectedStartup.command || "—") + "\nResolved file: " + (fileSense.selectedStartup.executable || "Unknown") + "\nArguments: " + (fileSense.selectedStartup.arguments || "—") + (fileSense.selectedStartup.stateNote ? "\n" + fileSense.selectedStartup.stateNote : "")
                                color: window.textMuted
                                font.pixelSize: 12
                                wrapMode: Text.WrapAnywhere
                                Layout.fillWidth: true
                            }
                            Text {
                                visible: fileSense.selectedStartup.entryId === undefined
                                text: "Select an entry above to view its details."
                                color: window.textMuted
                                font.pixelSize: 12
                                Layout.fillWidth: true
                                Layout.fillHeight: true
                                verticalAlignment: Text.AlignVCenter
                            }
                        }
                    }

                    RowLayout {
                        id: startupActionsRow
                        visible: window.activePage === "Startup Manager"
                        Layout.fillWidth: true
                        spacing: 10
                        StartupActionButton {
                            visible: true
                            enabled: fileSense.selectedStartup.disabledAction === true
                            primaryAction: enabled
                            iconText: "\uE769"
                            text: "Disable"
                            onClicked: {
                                startupActionDialog.enable = false;
                                startupActionDialog.open();
                            }
                        }
                        StartupActionButton {
                            visible: true
                            enabled: fileSense.selectedStartup.enabledAction === true
                            primaryAction: enabled
                            iconText: "\uE768"
                            text: "Enable / Restore"
                            onClicked: {
                                startupActionDialog.enable = true;
                                startupActionDialog.open();
                            }
                        }
                        AppButton {
                            visible: fileSense.selectedStartup.serviceEnableAction === true
                            text: "Enable service"
                            implicitHeight: 30
                            onClicked: fileSense.serviceAction(fileSense.selectedStartup.entryId, true)
                        }
                        AppButton {
                            visible: fileSense.selectedStartup.serviceDisableAction === true
                            text: "Disable service…"
                            implicitHeight: 30
                            onClicked: fileSense.serviceAction(fileSense.selectedStartup.entryId, false)
                        }
                        Item { Layout.fillWidth: true }
                    }

                    Rectangle {
                        visible: window.activePage === "Startup Manager" && fileSense.startupActionNotice.length > 0
                        Layout.fillWidth: true
                        implicitHeight: startupActionNoticeText.implicitHeight + 20
                        radius: 8
                        color: window.lightAppearance ? "#fff4e5" : "#332719"
                        border.color: window.lightAppearance ? "#e6a23c" : "#8d5b22"
                        Text {
                            id: startupActionNoticeText
                            anchors.fill: parent
                            anchors.margins: 10
                            text: fileSense.startupActionNotice
                            color: window.lightAppearance ? "#7a4300" : "#ffd08a"
                            font.pixelSize: 12
                            wrapMode: Text.WordWrap
                            verticalAlignment: Text.AlignVCenter
                        }
                    }

                    Item {
                        Layout.preferredHeight: 22
                    }
                }
            }
        }
    }

    Text {
        visible: window.activePage === "Home"
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        anchors.rightMargin: 28
        anchors.bottomMargin: 18
        text: "Crafted by <font color='#ff8a58'><b>Ankur</b></font> © <b>Prosoft</b>"
        textFormat: Text.RichText
        color: window.textMain
        font.pixelSize: 13
    }

    Popup {
        id: ruleDatePicker
        parent: Overlay.overlay
        property int conditionIndex: -1
        property string dateProperty: "startDate"
        property string targetField: ""
        property date displayedMonth: new Date()
        property date selectedDate: new Date()
        property var monthOptions: ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]
        property var yearOptions: {
            var years = [];
            var centerYear = displayedMonth.getFullYear();
            for (var year = centerYear - 100; year <= centerYear + 100; ++year)
                years.push(String(year));
            return years;
        }
        x: Math.max(8, (window.width - width) / 2)
        y: Math.max(8, (window.height - height) / 2)
        width: 276
        height: 326
        modal: true
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
        padding: 12
        function dateForCell(cellIndex) {
            var firstOfMonth = new Date(displayedMonth.getFullYear(), displayedMonth.getMonth(), 1);
            return new Date(displayedMonth.getFullYear(), displayedMonth.getMonth(), cellIndex - firstOfMonth.getDay() + 1);
        }
        background: Rectangle {
            radius: 12
            color: window.panel
            border.color: window.border
        }
        contentItem: ColumnLayout {
            spacing: 8
            RowLayout {
                Layout.fillWidth: true
                spacing: 4
                AppButton {
                    text: "‹"
                    Layout.preferredWidth: 30
                    Layout.preferredHeight: 30
                    onClicked: ruleDatePicker.displayedMonth = new Date(ruleDatePicker.displayedMonth.getFullYear(), ruleDatePicker.displayedMonth.getMonth() - 1, 1)
                }
                OrganizerComboBox {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 30
                    model: ruleDatePicker.monthOptions
                    currentIndex: ruleDatePicker.displayedMonth.getMonth()
                    onActivated: function (monthIndex) {
                        ruleDatePicker.displayedMonth = new Date(ruleDatePicker.displayedMonth.getFullYear(), monthIndex, 1);
                    }
                    contentItem: Text {
                        leftPadding: 8
                        rightPadding: 22
                        text: parent.displayText
                        color: window.textMain
                        font.pixelSize: 12
                        font.bold: true
                        horizontalAlignment: Text.AlignHCenter
                        verticalAlignment: Text.AlignVCenter
                        elide: Text.ElideRight
                    }
                    background: Rectangle {
                        radius: window.buttonRadius
                        color: window.panelRaised
                        border.color: window.border
                    }
                }
                OrganizerComboBox {
                    Layout.preferredWidth: 76
                    Layout.preferredHeight: 30
                    model: ruleDatePicker.yearOptions
                    currentIndex: model.indexOf(String(ruleDatePicker.displayedMonth.getFullYear()))
                    onActivated: function (yearIndex) {
                        ruleDatePicker.displayedMonth = new Date(Number(ruleDatePicker.yearOptions[yearIndex]), ruleDatePicker.displayedMonth.getMonth(), 1);
                    }
                    contentItem: Text {
                        leftPadding: 7
                        rightPadding: 22
                        text: parent.displayText
                        color: window.textMain
                        font.pixelSize: 12
                        font.bold: true
                        horizontalAlignment: Text.AlignHCenter
                        verticalAlignment: Text.AlignVCenter
                    }
                    background: Rectangle {
                        radius: window.buttonRadius
                        color: window.panelRaised
                        border.color: window.border
                    }
                }
                AppButton {
                    text: "›"
                    Layout.preferredWidth: 30
                    Layout.preferredHeight: 30
                    onClicked: ruleDatePicker.displayedMonth = new Date(ruleDatePicker.displayedMonth.getFullYear(), ruleDatePicker.displayedMonth.getMonth() + 1, 1)
                }
            }
            RowLayout {
                Layout.fillWidth: true
                spacing: 3
                Repeater {
                    model: ["Su", "Mo", "Tu", "We", "Th", "Fr", "Sa"]
                    delegate: Text {
                        required property string modelData
                        Layout.fillWidth: true
                        text: modelData
                        color: window.textMuted
                        font.pixelSize: 11
                        horizontalAlignment: Text.AlignHCenter
                    }
                }
            }
            GridLayout {
                Layout.fillWidth: true
                Layout.fillHeight: true
                columns: 7
                rowSpacing: 3
                columnSpacing: 3
                Repeater {
                    model: 42
                    delegate: Button {
                        required property int index
                        property date cellDate: ruleDatePicker.dateForCell(index)
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        padding: 0
                        text: String(cellDate.getDate())
                        onClicked: {
                            ruleDatePicker.selectedDate = cellDate;
                            if (ruleDatePicker.targetField !== "")
                                window.setSearchDateField(ruleDatePicker.targetField, Qt.formatDate(cellDate, "MM-dd-yyyy"));
                            else if (ruleDatePicker.conditionIndex >= 0 && ruleDatePicker.conditionIndex < ruleConditions.count)
                                ruleConditions.setProperty(ruleDatePicker.conditionIndex, ruleDatePicker.dateProperty, Qt.formatDate(cellDate, "MM-dd-yyyy"));
                            ruleDatePicker.close();
                        }
                        contentItem: Text {
                            text: parent.text
                            color: parent.cellDate.getMonth() === ruleDatePicker.displayedMonth.getMonth() ? window.textMain : window.textMuted
                            font.pixelSize: 12
                            horizontalAlignment: Text.AlignHCenter
                            verticalAlignment: Text.AlignVCenter
                        }
                        background: Rectangle {
                            radius: window.buttonRadius
                            color: parent.cellDate.getFullYear() === ruleDatePicker.selectedDate.getFullYear() && parent.cellDate.getMonth() === ruleDatePicker.selectedDate.getMonth() && parent.cellDate.getDate() === ruleDatePicker.selectedDate.getDate() ? window.accent : parent.hovered ? window.panelRaised : "transparent"
                        }
                    }
                }
            }
        }
    }

    FolderDialog {
        id: folderDialog
        property string target: "source"
        title: "Choose a folder"
        onAccepted: {
            var p = decodeURIComponent(selectedFolder.toString().replace("file:///", ""));
            if (target === "quickSource")
                quickSourcePath.text = p;
            else if (target === "quickExclude") {
                var exists = false;
                for (var i = 0; i < quickExcludedFolders.count; ++i) {
                    if (quickExcludedFolders.get(i).path.toLowerCase() === p.toLowerCase())
                        exists = true;
                }
                if (!exists)
                    quickExcludedFolders.append({
                        path: p
                    });
            } else if (target === "monitored")
                ruleMonitorPaths.text = ruleMonitorPaths.text ? ruleMonitorPaths.text + ";" + p : p;
            else if (target === "ruleDestination")
                ruleDestination.text = p;
            else if (target === "source")
                quickSourcePath.text = p;
            else if (target === "destination")
                ruleDestination.text = p;
            else if (target === "storage")
                storagePath.text = p;
            else if (target === "duplicateExclude") {
                addDuplicateExcludedFolder(p);
            } else if (target === "duplicates") {
                var existingDuplicateRoots = duplicateRoot.text ? duplicateRoot.text.split(";") : [];
                var duplicateFound = false;
                for (var j = 0; j < existingDuplicateRoots.length; ++j) {
                    if (existingDuplicateRoots[j].trim().toLowerCase() === p.toLowerCase()) duplicateFound = true;
                }
                if (!duplicateFound)
                    duplicateRoot.text = duplicateRoot.text ? duplicateRoot.text + ";" + p : p;
            }
            else if (target === "searchExclude") {
                addSearchExcludedFolder(p);
            } else if (target === "searchCopy") {
                fileSense.copySearchSelection(p);
            } else if (target === "searchMove") {
                fileSense.moveSearchSelection(p);
            } else
                appendSearchLocation(p);
        }
    }
    ThemedDialog {
        id: organizeConfirm
        title: "Organize these files?"
        acceptText: "Organize"
        contentItem: DialogMessage {
            message: "Files selected in the Quick Organize preview will be moved into category folders. Any existing destination file follows the per-row choice shown in the preview. Continue?"
            iconType: "question"
        }
        onAccepted: fileSense.organizeFiles()
    }
    ThemedDialog {
        id: ruleConfirm
        title: "Run this rule?"
        acceptText: "Run rule"
        contentItem: DialogMessage {
            message: "The matching files in the preview will be processed using “" + ruleAction.currentText + "”. Destination conflicts follow the per-row choices. Continue?"
            iconType: "question"
        }
        onAccepted: fileSense.runRule()
    }
    ThemedDialog {
        id: ruleDestinationDialog
        title: "Folder selection required"
        property string messageText: ""
        closeOnly: true
        showCancel: false
        contentItem: DialogMessage {
            message: ruleDestinationDialog.messageText
            iconType: "warning"
        }
    }
    ThemedDialog {
        id: storagePathDialog
        title: "Choose a drive or folder"
        closeOnly: true
        showCancel: false
        contentItem: DialogMessage {
            message: "Choose a drive or folder, or enter a path, before scanning storage."
            iconType: "info"
        }
    }
    ThemedDialog {
        id: cleanDialog
        title: "Clean selected categories?"
        acceptText: "Clean"
        contentItem: DialogMessage {
            message: "Selected candidates will be revalidated and moved to the Recycle Bin when possible. Continue?"
            iconType: "warning"
        }
        onAccepted: fileSense.cleanSelected()
    }
    ThemedDialog {
        id: cleanupResultsDialog
        title: "Cleanup results"
        acceptText: "Close"
        property string details: ""
        contentItem: DialogMessage {
            message: cleanupResultsDialog.details
            iconType: "info"
        }
    }
    ThemedDialog {
        id: activationDialog
        title: "Activate FileSense"
        width: 520
        height: 358
        padding: 0
        header: Rectangle {
            implicitHeight: 30
            color: window.lightAppearance ? window.panelRaised : "#101112"
            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 10
                anchors.rightMargin: 8
                spacing: 8
                Image {
                    source: "../assets/FSICO.png"
                    sourceSize.width: 18
                    sourceSize.height: 18
                    Layout.preferredWidth: 18
                    Layout.preferredHeight: 18
                    fillMode: Image.PreserveAspectFit
                }
                Text {
                    text: "Activate FileSense"
                    color: window.textMain
                    font.pixelSize: 12
                    Layout.fillWidth: true
                    verticalAlignment: Text.AlignVCenter
                }
                Rectangle {
                    Layout.preferredWidth: 28
                    Layout.preferredHeight: 28
                    radius: 6
                    color: closeHover.containsMouse ? (window.lightAppearance ? "#dedbd5" : "#252729") : "transparent"
                    Text {
                        anchors.centerIn: parent
                        text: "×"
                        color: window.textMain
                        font.pixelSize: 20
                    }
                    MouseArea {
                        id: closeHover
                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onClicked: activationDialog.reject()
                    }
                }
            }
        }
        contentItem: ColumnLayout {
            anchors.fill: parent
            anchors.margins: 18
            anchors.topMargin: 30
            spacing: 4
            Text {
                text: "Activate FileSense"
                color: window.textMain
                font.pixelSize: 18
                font.bold: true
            }
            Text {
                text: "Request an activation key for this device, then enter it below. Activation works offline."
                color: window.textMuted
                font.pixelSize: 12
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
            }
            Text {
                text: "Device activation code"
                color: window.textMain
                font.pixelSize: 12
                Layout.bottomMargin: -5
            }
            RowLayout {
                Layout.fillWidth: true
                DarkField {
                    text: fileSense.machineCode
                    readOnly: true
                    verticalAlignment: TextInput.AlignVCenter
                    topPadding: 0
                    bottomPadding: 0
                    Layout.fillWidth: true
                    Layout.preferredHeight: 36
                    implicitHeight: 36
                }
                DialogActionButton {
                    text: "Copy"
                    primary: false
                    Layout.preferredHeight: 32
                    onClicked: fileSense.copyMachineCode()
                }
            }
            Text {
                text: "Activation key"
                color: window.textMain
                font.pixelSize: 12
                Layout.bottomMargin: -5
            }
            DarkField {
                id: activationKey
                verticalAlignment: TextInput.AlignVCenter
                topPadding: 0
                bottomPadding: 0
                Layout.fillWidth: true
                Layout.preferredHeight: 36
                implicitHeight: 36
                placeholderText: "Paste your FileSense activation key"
            }
            RowLayout {
                Layout.fillWidth: true
                Layout.topMargin: 1
                Layout.bottomMargin: 7
                Item {
                    Layout.fillWidth: true
                }
                Text {
                    text: "☕ ₹99"
                    color: window.textMain
                    font.pixelSize: 14
                    font.bold: true
                    Layout.rightMargin: 8
                    Layout.alignment: Qt.AlignVCenter
                }
                DialogActionButton {
                    text: "Quit"
                    primary: false
                    Layout.preferredHeight: 32
                    onClicked: activationDialog.reject()
                }
                DialogActionButton {
                    text: "Activate"
                    coffee: true
                    Layout.preferredHeight: 32
                    onClicked: fileSense.activate(activationKey.text)
                }
            }
        }
        footer: Text {
            width: activationDialog.width
            height: 36
            text: "<span style='color:" + window.textMuted + "'>✦ Built with care. </span><span style='color:" + window.accent + "'>Powered by your support.</span>"
            textFormat: Text.RichText
            color: window.textMuted
            font.pixelSize: 11
            horizontalAlignment: Text.AlignHCenter
            verticalAlignment: Text.AlignVCenter
        }
        onRejected: if (fileSense.licenseExpired)
            activationDialog.open()
    }
    ThemedDialog {
        id: activationThanksDialog
        title: "Thank you!"
        acceptText: "Enjoy FileSense"
        showCancel: false
        contentItem: DialogMessage {
            message: "Thank you for the coffee! Enjoy FileSense — you're officially unlocked! 🎉"
            iconType: "success"
        }
    }
    ThemedDialog {
        id: startupActionDialog
        property bool enable: false
        title: enable ? "Enable startup item?" : "Disable startup item?"
        acceptText: enable ? "Enable" : "Disable"
        contentItem: DialogMessage {
            message: (startupActionDialog.enable ? "Restore" : "Disable") + " this startup entry? FileSense keeps restore data so it can be re-enabled."
            iconType: "warning"
        }
        onAccepted: fileSense.startupAction(fileSense.selectedStartup.entryId, enable)
    }
    ThemedDialog {
        id: startupConfirmationDialog
        property string message: ""
        title: "Confirm startup change"
        acceptText: "Continue"
        contentItem: DialogMessage {
            message: startupConfirmationDialog.message
            iconType: "warning"
        }
        onAccepted: fileSense.respondToConfirmation(true)
        onRejected: fileSense.respondToConfirmation(false)
    }
    ThemedDialog {
        id: startupActionErrorDialog
        property string message: ""
        title: message.indexOf("administrator privileges") >= 0
               ? "Administrator privileges required" : "Could not update startup item"
        acceptText: "Close"
        showCancel: false
        contentItem: DialogMessage {
            message: startupActionErrorDialog.message
            iconType: "warning"
        }
    }
    ThemedDialog {
        id: duplicateConfirm
        title: "Delete checked entries?"
        acceptText: "Move to Recycle Bin"
        contentItem: DialogMessage {
            message: fileSense.duplicateConfirmationText
            iconType: "warning"
        }
        onAccepted: fileSense.resolveDuplicates(duplicateMode === "Build a rule" ? "rule" : "find")
    }
    Connections {
        target: fileSense
        function onStartupActionFailed(message) {
            startupActionErrorDialog.message = message;
            startupActionErrorDialog.open();
        }
        function onConfirmationRequested(title, message) {
            startupConfirmationDialog.title = title;
            startupConfirmationDialog.acceptText = title === "Delete selected search results?" ? "Delete" : "Continue";
            startupConfirmationDialog.message = message;
            startupConfirmationDialog.open();
        }
        function onCleanupCompleted(details) {
            cleanupResultsDialog.details = details;
            cleanupResultsDialog.open();
        }
        function onChanged() {
            if (fileSense.status === "Activated." && !window.activationThankYouShown) {
                window.activationThankYouShown = true;
                activationDialog.close();
                activationThanksDialog.open();
            }
        }
    }
    Shortcut {
        sequence: "Ctrl+Shift+A"
        onActivated: activationDialog.open()
    }

    onActivePageChanged: {
        contentColumn.opacity = 0.78;
        fadeRestart.restart();
    }
    Component.onCompleted: if (fileSense.licenseExpired)
        activationDialog.open()
    Timer {
        id: fadeRestart
        interval: 80
        onTriggered: contentColumn.opacity = 1
    }
}
