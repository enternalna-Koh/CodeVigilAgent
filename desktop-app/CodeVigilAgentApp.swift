import Cocoa
import Darwin
import UniformTypeIdentifiers

private enum AgentTask {
    case chat(String, String)
    case review
    case sessionsList(String)
    case sessionShow(String)
    case sessionRename(String, String)
    case sessionDelete(String)
    case sessionExport(String, String)
}

private struct HistoryRow {
    let name: String
    let title: String
    let summary: String
    let updatedAt: String
    let turns: Int
    let repository: String
    let status: String

    init(_ data: [String: Any]) {
        name = data["name"] as? String ?? ""
        title = data["title"] as? String ?? name
        summary = data["summary"] as? String ?? ""
        updatedAt = data["saved_at"] as? String ?? ""
        // CLI 的 list_sessions 把 turns 统一 str() 成字符串返回；顺手接住数字形态，容错为 0
        if let number = data["turns"] as? Int {
            turns = number
        } else {
            turns = Int(data["turns"] as? String ?? "") ?? 0
        }
        repository = data["repository"] as? String ?? ""
        status = data["status"] as? String ?? "completed"
    }
}

// 历史列表单条样式（对齐设计稿）：
//   第一行 主标题：会话标题（或首个用户提问）截断到 28 字，尾部 …
//   第二行 副标题：日期 + 参与轮次，如「2026-11-13 · 4 轮」
//   第三行 预览：最后一条消息内容截断到 60 字（CLI 的 summary 已按
//          「最后一条非空消息」取值，成功会话即最后一条 Agent 回复；
//          失败会话自然回退成最后一条用户提问），完整时间放 toolTip
private final class HistoryCell: NSTableCellView {
    private let title = NSTextField(labelWithString: "")
    private let subtitle = NSTextField(labelWithString: "")
    private let preview = NSTextField(labelWithString: "")

    override init(frame frameRect: NSRect) {
        super.init(frame: frameRect)
        title.font = .systemFont(ofSize: 12, weight: .semibold)
        title.lineBreakMode = .byTruncatingTail
        subtitle.font = .systemFont(ofSize: 10)
        subtitle.textColor = .secondaryLabelColor
        subtitle.lineBreakMode = .byTruncatingTail
        preview.font = .systemFont(ofSize: 11)
        preview.textColor = .secondaryLabelColor
        preview.lineBreakMode = .byTruncatingTail
        [title, subtitle, preview].forEach {
            $0.translatesAutoresizingMaskIntoConstraints = false
            addSubview($0)
        }
        NSLayoutConstraint.activate([
            title.leadingAnchor.constraint(equalTo: leadingAnchor, constant: 8),
            title.trailingAnchor.constraint(equalTo: trailingAnchor, constant: -8),
            title.topAnchor.constraint(equalTo: topAnchor, constant: 6),
            subtitle.leadingAnchor.constraint(equalTo: leadingAnchor, constant: 8),
            subtitle.trailingAnchor.constraint(equalTo: trailingAnchor, constant: -8),
            subtitle.topAnchor.constraint(equalTo: title.bottomAnchor, constant: 3),
            preview.leadingAnchor.constraint(equalTo: leadingAnchor, constant: 8),
            preview.trailingAnchor.constraint(equalTo: trailingAnchor, constant: -8),
            preview.topAnchor.constraint(equalTo: subtitle.bottomAnchor, constant: 3),
            preview.bottomAnchor.constraint(lessThanOrEqualTo: bottomAnchor, constant: -5),
        ])
    }

    required init?(coder: NSCoder) { nil }

    func configure(_ row: HistoryRow) {
        title.stringValue = row.title.count > 28 ? String(row.title.prefix(28)) + "…" : row.title
        let date = String(row.updatedAt.replacingOccurrences(of: "T", with: " ").prefix(10))
        subtitle.stringValue = row.turns > 0 ? "\(date) · \(row.turns) 轮" : date
        if row.summary.isEmpty {
            preview.stringValue = "（空对话）"
        } else {
            preview.stringValue = row.summary.count > 60
                ? String(row.summary.prefix(60)) + "…" : row.summary
        }
        toolTip = "\(row.title)\n\(row.updatedAt)\n\(row.repository)\n\(row.status)"
    }

    /// 仿 WorkBuddy 历史下拉：当前选中的会话标题用主色，其余行标题灰色。
    func setEmphasized(_ emphasized: Bool) {
        title.textColor = emphasized ? .labelColor : .secondaryLabelColor
    }
}

private final class ProcessOutput {
    private let lock = NSLock()
    private var stdout = Data()
    private var stderr = Data()

    func append(_ data: Data, isError: Bool) {
        lock.lock()
        if isError { stderr.append(data) } else { stdout.append(data) }
        lock.unlock()
    }

    func values() -> (Data, Data) {
        lock.lock()
        defer { lock.unlock() }
        return (stdout, stderr)
    }
}

private final class ReaderCompletion {
    private let lock = NSLock()
    private let group: DispatchGroup
    private var finished = false

    init(_ group: DispatchGroup) { self.group = group }

    func finish() {
        lock.lock()
        defer { lock.unlock() }
        guard !finished else { return }
        finished = true
        group.leave()
    }
}

// MARK: - 模型清单（唯一来源：Python 侧 scripts/model_catalog.py 的 CATALOG）
//
// 桌面端不维护第二份模型列表，也不在这里写死厂家/模型名：
// 打开「模型设置」时调用
//     python ascend_cli.py model --list --json
// 把返回的 JSON 解析成两个下拉框的选项。
// Swift 里只保留 ModelSettingsForm 里那一个极小的兜底字符串，见下方注释。

private struct ModelCatalogEntry {
    let label: String
    let fileProvider: String
    let baseURL: String
    let models: [String]
    let defaultModel: String
    let aliases: [String]
    let isCurrent: Bool

    init?(_ raw: [String: Any]) {
        guard let label = raw["label"] as? String, !label.isEmpty,
              let fileProvider = raw["file_provider"] as? String,
              let models = raw["models"] as? [String], !models.isEmpty else { return nil }
        self.label = label
        self.fileProvider = fileProvider
        self.baseURL = raw["base_url"] as? String ?? ""
        self.models = models
        let fallbackDefault = raw["default_model"] as? String ?? ""
        self.defaultModel = models.contains(fallbackDefault) ? fallbackDefault : models[0]
        self.aliases = raw["aliases"] as? [String] ?? []
        self.isCurrent = raw["current"] as? Bool ?? false
    }

    /// 下拉框标题：厂商名 + 一个别名，别名同样来自 catalog（例如 glm（智谱））。
    /// 优先中文别名，中文用户更好认；与 Python 侧 scripts/model_choices.py 的规则一致。
    var displayTitle: String {
        let others = aliases.filter { $0.lowercased() != label.lowercased() }
        guard !others.isEmpty else { return label }
        let alias = others.first { $0.unicodeScalars.contains { $0.value > 127 } } ?? others[0]
        return "\(label)（\(alias)）"
    }

    /// 配置文件里存的 provider 可能是 label / file_provider / alias，都要能对上。
    func matches(provider: String) -> Bool {
        let name = provider.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        if name.isEmpty { return false }
        return name == label.lowercased()
            || name == fileProvider.lowercased()
            || aliases.contains { $0.lowercased() == name }
    }
}

private struct ModelCatalog {
    let entries: [ModelCatalogEntry]
    let activeProvider: String
    let activeModel: String
    let activeBaseURL: String

    static func parse(_ data: Data) -> ModelCatalog? {
        guard let root = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any],
              let rawEntries = root["catalog"] as? [[String: Any]] else { return nil }
        let entries = rawEntries.compactMap(ModelCatalogEntry.init)
        guard !entries.isEmpty else { return nil }
        let active = root["active"] as? [String: Any] ?? [:]
        return ModelCatalog(entries: entries,
                            activeProvider: active["provider"] as? String ?? "",
                            activeModel: active["model"] as? String ?? "",
                            activeBaseURL: active["base_url"] as? String ?? "")
    }
}

private struct ModelCatalogLoad {
    let catalog: ModelCatalog?
    let error: String
}

private enum ModelCatalogLoader {
    /// 调用 CLI 取清单。失败时返回 (nil, 原因)，调用方负责降级成手动输入。
    static func load(pythonPath: String?, backend: URL,
                     environment: [String: String]) -> ModelCatalogLoad {
        guard let pythonPath = pythonPath else {
            return ModelCatalogLoad(catalog: nil, error: "找不到 Python 3")
        }
        let process = Process()
        let stdout = Pipe()
        let stderr = Pipe()
        process.executableURL = URL(fileURLWithPath: pythonPath)
        process.currentDirectoryURL = backend
        process.arguments = [backend.appendingPathComponent("ascend_cli.py").path,
                             "model", "--list", "--json"]
        process.standardOutput = stdout
        process.standardError = stderr
        process.environment = environment
        do {
            try process.run()
        } catch {
            return ModelCatalogLoad(catalog: nil, error: error.localizedDescription)
        }
        // 清单只有几 KB，先读完管道再等退出，不会把子进程的缓冲区塞满
        let outputData = stdout.fileHandleForReading.readDataToEndOfFile()
        let errorData = stderr.fileHandleForReading.readDataToEndOfFile()
        process.waitUntilExit()
        guard process.terminationStatus == 0 else {
            let detail = (String(data: errorData, encoding: .utf8) ?? "")
                .trimmingCharacters(in: .whitespacesAndNewlines)
            let reason = detail.isEmpty ? "退出码 \(process.terminationStatus)"
                                        : "退出码 \(process.terminationStatus)：\(detail)"
            return ModelCatalogLoad(catalog: nil, error: reason)
        }
        guard let catalog = ModelCatalog.parse(outputData) else {
            return ModelCatalogLoad(catalog: nil, error: "返回内容不是合法的 JSON 清单")
        }
        return ModelCatalogLoad(catalog: catalog, error: "")
    }
}

// MARK: - 模型设置表单
//
// 两个下拉框（厂商 / 模型），选项全部来自上面的 catalog；
// 「自定义模型」用于私有部署等清单里没有的模型名。
// 读不到清单时降级成「模型 ID」文本框，并保留原有配置不动。

private final class ModelSettingsForm: NSObject, NSTextFieldDelegate {
    static let customModelTitle = "自定义模型…"

    private(set) var grid = NSGridView(views: [[NSView()]])
    let keyField = NSSecureTextField(string: "")

    private let providerPopup = NSPopUpButton(frame: .zero, pullsDown: false)
    private let modelPopup = NSPopUpButton(frame: .zero, pullsDown: false)
    private let customModelField = NSTextField(string: "")
    private let baseURLField = NSTextField(string: "")
    private let hintLabel = NSTextField(wrappingLabelWithString: "")

    private var displayedEntries: [ModelCatalogEntry?] = []
    private var displayedModels: [String] = []

    private let existingProvider: String
    private let existingModel: String
    /// 打开对话框时的 base_url / 密钥：用来判断用户是否真的换了厂商，
    /// 切回原厂商时把原密钥填回去。
    private let existingBaseURL: String
    private let savedKey: String
    private var keyGateway: [String]
    private var keyMissing = false
    /// selection() 失败的原因，供调用方原样显示（比固定文案准确）
    private(set) var validationError: String?

    init(existing: [String: Any], load: ModelCatalogLoad) {
        existingProvider = (existing["provider"] as? String ?? "")
            .trimmingCharacters(in: .whitespacesAndNewlines)
        existingModel = (existing["model"] as? String ?? "")
            .trimmingCharacters(in: .whitespacesAndNewlines)
        existingBaseURL = (existing["base_url"] as? String ?? "")
            .trimmingCharacters(in: .whitespacesAndNewlines)
        savedKey = existing["api_key"] as? String ?? ""
        keyGateway = Self.gateway(provider: existingProvider.isEmpty ? "deepseek" : existingProvider,
                                  baseURL: existingBaseURL)
        super.init()
        buildViews(existing: existing, load: load)
    }

    private func buildViews(existing: [String: Any], load: ModelCatalogLoad) {
        let existingBase = (existing["base_url"] as? String ?? "")
            .trimmingCharacters(in: .whitespacesAndNewlines)

        baseURLField.stringValue = existingBase
        baseURLField.placeholderString = "默认地址（可留空）"
        keyField.placeholderString = "留空以保留现有密钥"
        keyField.stringValue = savedKey
        customModelField.placeholderString = "清单里没有的模型名（私有部署用）"
        // 自定义模型框始终可编辑；打字时会自动把模型下拉切到「自定义模型…」
        customModelField.delegate = self
        baseURLField.delegate = self

        let providerLabel = NSTextField(labelWithString: "服务商")
        let modelLabel = NSTextField(labelWithString: "模型")
        let customLabel = NSTextField(labelWithString: "自定义模型")
        let baseLabel = NSTextField(labelWithString: "API 地址")
        let keyLabel = NSTextField(labelWithString: "API Key")

        var views: [[NSView]] = []
        if let catalog = load.catalog {
            views = [
                [providerLabel, providerPopup],
                [modelLabel, modelPopup],
                [customLabel, customModelField],
                [baseLabel, baseURLField],
                [keyLabel, keyField],
            ]
            // 优先用 CLI 算好的 current：kimi / gemini / qwen 等的 file_provider 都是 openai，
            // 只按 provider 匹配会把它们错认成 openai，必须靠 base_url 区分
            let preferred = catalog.entries.first(where: { $0.isCurrent })
                ?? catalog.entries.first(where: { $0.matches(provider: existingProvider) })
                ?? catalog.entries[0]
            for (index, entry) in catalog.entries.enumerated() {
                providerPopup.addItem(withTitle: entry.displayTitle)
                displayedEntries.append(entry)
                if entry.label == preferred.label { providerPopup.selectItem(at: index) }
            }
            let known = catalog.entries.contains(where: { $0.isCurrent || $0.matches(provider: existingProvider) })
            if !existingProvider.isEmpty, !known {
                // 配置里的厂商不在清单中：保留原值，避免只打开对话框就把它改掉
                providerPopup.insertItem(withTitle: "保持原值（\(existingProvider)）", at: 0)
                displayedEntries.insert(nil, at: 0)
                providerPopup.selectItem(at: 0)
            }
            populateModels(for: selectedEntry(), preferred: existingModel)
            hintLabel.stringValue = ""   // 平时不摆说明文字，只在出错时占位
            hintLabel.textColor = .secondaryLabelColor
        } else {
            // 读不到清单 → 手动输入模式，原有配置原样保留
            modelLabel.stringValue = "模型 ID"
            views = [
                [modelLabel, customModelField],
                [baseLabel, baseURLField],
                [keyLabel, keyField],
            ]
            customModelField.stringValue = existingModel
            hintLabel.stringValue = "无法读取模型清单（\(load.error)），已改为手动输入；保存不会改动其它配置。"
            hintLabel.textColor = .systemRed
        }

        views.append([NSTextField(labelWithString: ""), hintLabel])
        grid = NSGridView(views: views)
        grid.columnSpacing = 12
        grid.rowSpacing = 10
        // 最后一行是提示，可能换行成两行，单独给 44pt，避免错误信息被裁掉
        let hintRow = views.count - 1
        grid.row(at: hintRow).height = 44
        hintLabel.maximumNumberOfLines = 2
        hintLabel.preferredMaxLayoutWidth = 300
        grid.frame = NSRect(x: 0, y: 0, width: 440,
                            height: CGFloat(hintRow) * 24 + CGFloat(hintRow) * 10 + 44)
        for control in [providerPopup, modelPopup, customModelField, baseURLField, keyField, hintLabel] as [NSView] {
            control.widthAnchor.constraint(equalToConstant: 300).isActive = true
        }
        providerPopup.target = self
        providerPopup.action = #selector(providerChanged(_:))
        modelPopup.target = self
        modelPopup.action = #selector(modelChanged(_:))
    }

    /// 保存校验失败时把原因写进对话框，而不是让对话框直接关掉、用户白填一遍
    func showHint(_ text: String, color: NSColor = .systemRed) {
        hintLabel.stringValue = text
        hintLabel.textColor = color
    }

    /// 问题解决了就把这一行收回去，别让它常驻在界面上
    func hideHint() {
        hintLabel.stringValue = ""
    }

    private func selectedEntry() -> ModelCatalogEntry? {
        let index = providerPopup.indexOfSelectedItem
        guard displayedEntries.indices.contains(index) else { return nil }
        return displayedEntries[index]
    }

    private func populateModels(for entry: ModelCatalogEntry?, preferred: String) {
        displayedModels = entry?.models ?? []
        modelPopup.removeAllItems()
        if !displayedModels.isEmpty {
            modelPopup.addItems(withTitles: displayedModels)
        }
        modelPopup.addItem(withTitle: ModelSettingsForm.customModelTitle)
        // 自定义框一直可编辑，所以这里只改文字，不碰 isEnabled
        customModelField.stringValue = ""

        let wanted = preferred.trimmingCharacters(in: .whitespacesAndNewlines)
        if !wanted.isEmpty {
            if let index = displayedModels.firstIndex(of: wanted) {
                modelPopup.selectItem(at: index)
            } else {
                // 当前模型不在清单里也要正确回显，不强行改成 default_model
                modelPopup.selectItem(at: displayedModels.count)
                customModelField.stringValue = wanted
            }
            return
        }
        guard let entry = entry else {
            modelPopup.selectItem(at: displayedModels.count)
            return
        }
        if let index = displayedModels.firstIndex(of: entry.defaultModel) {
            modelPopup.selectItem(at: index)
        }
    }

    @objc private func providerChanged(_ sender: NSPopUpButton) {
        let entry = selectedEntry()
        // 切厂商时自动带出该厂商的 base_url；用户之后仍可手动改
        baseURLField.stringValue = entry?.baseURL ?? existingBaseURL
        populateModels(for: entry, preferred: entry == nil ? existingModel : "")
        syncKeyForGateway()
    }

    private static func gateway(provider: String, baseURL: String) -> [String] {
        var base = baseURL.trimmingCharacters(in: .whitespacesAndNewlines)
        while base.hasSuffix("/") { base.removeLast() }
        return [provider.trimmingCharacters(in: .whitespacesAndNewlines).lowercased(), base]
    }

    private func syncKeyForGateway() {
        let provider = selectedEntry()?.fileProvider
            ?? (existingProvider.isEmpty ? "deepseek" : existingProvider)
        let target = Self.gateway(provider: provider, baseURL: baseURLField.stringValue)
        let original = Self.gateway(provider: existingProvider.isEmpty ? "deepseek" : existingProvider,
                                    baseURL: existingBaseURL)
        if target != keyGateway {
            keyGateway = target
            keyField.stringValue = target == original ? savedKey : ""
        }
        keyMissing = target != original
        if keyMissing {
            showHint("服务商或 API 地址已变更\n请填写该地址对应的 API Key。")
        } else if !displayedEntries.isEmpty {
            showHint("模型清单来自终端 CLI（\(displayedEntries.count) 个厂商）。", color: .secondaryLabelColor)
        }
    }

    @objc private func modelChanged(_ sender: NSPopUpButton) {
        let isCustom = sender.indexOfSelectedItem >= displayedModels.count
        if !isCustom {
            // 选回清单里的模型 → 清掉手填内容，避免残留值让人误会
            customModelField.stringValue = ""
        }
    }

    /// 在「自定义模型」里打字 → 模型下拉自动跳到「自定义模型…」。
    /// 这样用户不用先在下拉里选一次，保存时也一定用的是他写的名字。
    func controlTextDidChange(_ obj: Notification) {
        guard let field = obj.object as? NSTextField else { return }
        if field === baseURLField {
            syncKeyForGateway()
            return
        }
        guard field === customModelField else { return }
        let text = field.stringValue.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty else { return }
        if modelPopup.indexOfSelectedItem != displayedModels.count {
            modelPopup.selectItem(at: displayedModels.count)
        }
    }

    /// 读回用户的选择；模型为空 / 换了厂商却没填密钥时返回 nil。
    /// 失败原因写进 validationError，调用方原样显示即可。
    func selection() -> (provider: String, model: String, baseURL: String)? {
        validationError = nil
        syncKeyForGateway()
        let modelIndex = modelPopup.indexOfSelectedItem
        // 手填框有内容就以它为准（和 Windows 端 prefer_custom 规则一致）；
        // 否则命中清单取下拉项，落在「自定义模型…」取文本框
        var model = customModelField.stringValue
            .trimmingCharacters(in: .whitespacesAndNewlines)
        if model.isEmpty, displayedModels.indices.contains(modelIndex) {
            model = displayedModels[modelIndex]
        }
        guard !model.isEmpty else {
            validationError = "模型不能为空\n请在下拉里选一个，或选「自定义模型…」后填写名称。"
            return nil
        }
        let key = keyField.stringValue.trimmingCharacters(in: .whitespacesAndNewlines)
        if keyMissing, key.isEmpty {
            validationError = "还没填新服务商或地址的 API Key\n请填写后再保存。"
            return nil
        }
        // 「保持原值」场景下 provider 沿用配置里的值；两者都空时用内置默认，避免写空字符串
        let provider = selectedEntry()?.fileProvider
            ?? (existingProvider.isEmpty ? "deepseek" : existingProvider)
        return (provider,
                model,
                baseURLField.stringValue.trimmingCharacters(in: .whitespacesAndNewlines))
    }

    /// 保存时写进配置的注释字段（配置里的 label 只是给人看的）。
    func selectedLabel() -> String? {
        selectedEntry()?.label
    }
}

// MARK: - 输出区排版
//
// 输出区显示的是终端文本，里面有框线（╭ ─ │ ╯）、缩进和箭头，必须严格按
// 「一个字符一格」排。原来用 .systemFont(ofSize: 14)，那是 SF Pro，**比例字体**，
// 每个字母宽度都不一样，于是：
//   1. 框线竖线落在汉字的笔画中间 —— 看起来就是「中文字体重合」；
//   2. 汉字比拉丁字母高，NSTextView 按拉丁字体算行高，中文上下会被压到相邻行；
//   3. 中英文混排时左右边界参差不齐，一行的右边框能跑到另一行的边框外面。
//
// 这里统一成：
//   西文 12pt SF Mono（等宽，1 格）+ 汉字「正好两格宽」的字号 + 固定行高。
private enum TerminalStyle {
    /// 西文等宽字体。所有字符同宽，这是字符网格的地基。
    static let mono = NSFont.monospacedSystemFont(ofSize: 12, weight: .regular)
    static let monoBold = NSFont.monospacedSystemFont(ofSize: 12, weight: .semibold)

    /// 一个西文字符的宽度。等宽字体里所有字符同宽，测一个 "M" 就够。
    static let cell: CGFloat = ("M" as NSString).size(withAttributes: [.font: mono]).width

    /// 汉字 / 全角标点用的字体：字号放大到「正好两格」。
    /// 汉字在终端里本来就占两格，用 1em 的字号渲染会永远对不齐框线。
    static let cjk: NSFont = {
        let size = max(cell * 2, 13)
        // 先写 PostScript 名（最可靠），再写 family 名兜底。
        let candidates = ["PingFangSC-Regular", "PingFang SC",
                          "HiraginoSansGB-W3", "Hiragino Sans GB",
                          "Heiti SC", "Songti SC"]
        for name in candidates {
            if let font = NSFont(name: name, size: size) { return font }
        }
        // 系统里没有中文字体时退回默认，至少不会崩。
        return NSFont.systemFont(ofSize: size)
    }()

    /// 固定行高。取两种字体里更高的那个再留 4pt 余量。
    /// 不锁定行高的话，含汉字的行会比纯英文行高，行与行之间就会挤在一起。
    static let lineHeight: CGFloat = {
        let latin = mono.ascender - mono.descender + mono.leading
        let han = cjk.ascender - cjk.descender + cjk.leading
        return ceil(max(latin, han)) + 4
    }()

    static func paragraph() -> NSParagraphStyle {
        let style = NSMutableParagraphStyle()
        style.minimumLineHeight = lineHeight
        style.maximumLineHeight = lineHeight
        style.lineBreakMode = .byWordWrapping
        return style
    }

    /// 需要占两格的字符：汉字、全角标点、谚文、假名、CJK 符号，
    /// 外加几个在中文终端里同样按两列排的符号（中点 ·、省略号 …、箭头 →）。
    ///
    /// 这份规则必须和 Python 侧 scripts/term_frame.char_width 保持一致 ——
    /// 输出文本里的空格数是 CLI 按那套规则补好的，这里若少算一格，
    /// 整行就会短一格，右边框会往左缩。
    ///
    /// 制表符 ╭─│╯（U+2500 段）刻意**不**算两格，它们在等宽字体里本来就是 1 格；
    /// 勾 ✓ 叉 ✗ 也是 1 格，和终端一致。
    static func isDoubleWidth(_ code: unichar) -> Bool {
        switch code {
        case 0x00B4, 0x00B7,               // ´ · 中点
             0x00D7,                       // × 乘号
             0x2013, 0x2014,               // – — 连接号
             0x2026,                       // … 省略号
             0x2460...0x2463,              // ①②③④
             0x2580...0x258F,              // ▌█ 方块（进度条、章节符号）
             0x25C6, 0x25C7,               // ◆ ◇
             0x25CB, 0x25CF,               // ○ ●
             0x2605, 0x2606,               // ★ ☆
             0x2665,                       // ♥
             0x2705,                       // ✅
             0x2190...0x2199,              // ← ↑ → ↓ 等箭头
             0x1100...0x115F,              // 谚文字母
             0x2E80...0x2FDF,              // CJK 部首
             0x2FF0...0x303E,              // 表意文字描述符 / CJK 符号与标点
             0x3041...0x33FF,              // 假名、注音、CJK 兼容
             0x3400...0x4DBF,              // CJK 扩展 A
             0x4E00...0x9FFF,              // CJK 基本区（常用汉字）
             0xA000...0xA4CF,              // 彝文
             0xAC00...0xD7A3,              // 谚文音节
             0xF900...0xFAFF,              // CJK 兼容表意文字
             0xFE10...0xFE19,              // 竖排标点
             0xFE30...0xFE6F,              // CJK 兼容形式
             0xFF01...0xFF60,              // 全角 ASCII / 全角标点
             0xFFE0...0xFFE6:              // 全角符号
            return true
        default:
            return false
        }
    }

    /// 把一段纯文本包成「西文等宽 + 汉字双倍宽 + 固定行高」的富文本。
    static func attributed(_ text: String, color: NSColor, bold: Bool) -> NSAttributedString {
        let base: [NSAttributedString.Key: Any] = [
            .font: bold ? monoBold : mono,
            .foregroundColor: color,
            .paragraphStyle: paragraph(),
        ]
        let result = NSMutableAttributedString(string: text, attributes: base)
        let ns = text as NSString
        var index = 0
        while index < ns.length {
            if isDoubleWidth(ns.character(at: index)) {
                result.addAttribute(.font, value: cjk,
                                    range: NSRange(location: index, length: 1))
            }
            index += 1
        }
        return result
    }
}

final class CodeVigilAgentDelegate: NSObject, NSApplicationDelegate, NSWindowDelegate,
                                    NSTableViewDataSource, NSTableViewDelegate {
    private var window: NSWindow!
    private let repositoryField = NSTextField()
    private let promptField = NSTextField()
    private let outputView = NSTextView()
    private let statusLabel = NSTextField(labelWithString: "就绪")
    private let historySearchField = NSSearchField()
    private let historyTableView = NSTableView()
    private var sendButton: NSButton!
    private var cancelButton: NSButton!
    private var newConversationButton: NSButton!
    private var clearDisplayButton: NSButton!
    private var renameSessionButton: NSButton!
    private var deleteSessionButton: NSButton!
    private var exportSessionButton: NSButton!
    private var actionButtons: [NSButton] = []
    private var historyRows: [HistoryRow] = []
    private var currentSessionName: String?
    private var currentTitle = "新对话"
    private var currentMessages: [[String: Any]] = []
    private var openSessionAfterRefresh: String?
    private var suppressHistorySelection = false
    private var searchWorkItem: DispatchWorkItem?
    private var runningProcess: Process?
    private var runningPipes: [Pipe] = []
    private var runningReaders: DispatchGroup?
    private var runningReaderCompletions: [ReaderCompletion] = []
    private var activeTaskID: UUID?
    private var cancelRequested = false
    private var statusAfterHistoryRefresh: String?
    private var sessionID = UUID().uuidString
    private var sessionRepository = ""

    func applicationDidFinishLaunching(_ notification: Notification) {
        buildWindow()
        repositoryField.stringValue = UserDefaults.standard.string(forKey: "lastRepositoryPath") ?? ""
        sessionRepository = repositoryField.stringValue
        refreshSessions()
        NSApp.activate(ignoringOtherApps: true)
        window.makeKeyAndOrderFront(nil)
    }

    func applicationWillTerminate(_ notification: Notification) {
        stopProcessForTermination()
    }

    func windowWillClose(_ notification: Notification) {
        stopProcessForTermination()
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool {
        true
    }

    private func buildWindow() {
        let content = NSView()
        content.translatesAutoresizingMaskIntoConstraints = false
        content.wantsLayer = true
        content.layer?.backgroundColor = NSColor(calibratedWhite: 0.07, alpha: 1).cgColor

        let title = NSTextField(labelWithString: "CodeVigil Agent")
        title.font = .systemFont(ofSize: 25, weight: .semibold)
        title.textColor = NSColor(calibratedRed: 0.48, green: 0.92, blue: 0.78, alpha: 1)

        let subtitle = NSTextField(labelWithString: "昇腾 AI Infra 代码审查与问题诊断")
        subtitle.font = .systemFont(ofSize: 13)
        subtitle.textColor = NSColor(calibratedWhite: 0.62, alpha: 1)

        statusLabel.font = .systemFont(ofSize: 12, weight: .medium)
        statusLabel.textColor = NSColor(calibratedWhite: 0.72, alpha: 1)
        statusLabel.alignment = .right

        let header = NSStackView(views: [title, subtitle, statusLabel])
        header.orientation = .horizontal
        // 25pt 英文和 13pt 中文按 centerY 对齐时，汉字会浮在英文上半部，
        // 看起来像「压在标题上」。按最后一行基线对齐才自然。
        header.alignment = .lastBaseline
        header.spacing = 14
        header.setCustomSpacing(22, after: subtitle)
        title.setContentHuggingPriority(.required, for: .horizontal)
        // 副标题允许被压缩并显示省略号：窗口收窄时三个标签不会挤成一团。
        subtitle.setContentHuggingPriority(.defaultLow, for: .horizontal)
        subtitle.setContentCompressionResistancePriority(.defaultLow, for: .horizontal)
        subtitle.lineBreakMode = .byTruncatingTail
        statusLabel.setContentHuggingPriority(.required, for: .horizontal)
        statusLabel.setContentCompressionResistancePriority(.required, for: .horizontal)

        repositoryField.placeholderString = "选择要审查的 Git 仓库目录"
        repositoryField.font = .systemFont(ofSize: 13)
        repositoryField.textColor = NSColor(calibratedWhite: 0.9, alpha: 1)
        repositoryField.backgroundColor = NSColor(calibratedWhite: 0.12, alpha: 1)
        repositoryField.isBezeled = true
        repositoryField.bezelStyle = .roundedBezel
        repositoryField.translatesAutoresizingMaskIntoConstraints = false

        let chooseButton = makeButton("选择目录", action: #selector(chooseRepository))
        let repoLabel = NSTextField(labelWithString: "仓库")
        repoLabel.font = .systemFont(ofSize: 13, weight: .medium)
        repoLabel.textColor = NSColor(calibratedWhite: 0.78, alpha: 1)
        repoLabel.setContentHuggingPriority(.required, for: .horizontal)

        let repoRow = NSStackView(views: [repoLabel, repositoryField, chooseButton])
        repoRow.orientation = .horizontal
        repoRow.alignment = .centerY
        repoRow.spacing = 10
        repositoryField.setContentCompressionResistancePriority(.defaultLow, for: .horizontal)

        let reviewButton = makeButton("审查当前改动", action: #selector(reviewChanges))
        let offlineButton = makeButton("离线审查", action: #selector(offlineReview))
        let settingsButton = makeButton("模型设置", action: #selector(configureModel))
        let actionRow = NSStackView(views: [reviewButton, offlineButton, settingsButton])
        actionRow.orientation = .horizontal
        actionRow.alignment = .centerY
        actionRow.spacing = 10
        actionButtons = [reviewButton, offlineButton, settingsButton]

        outputView.isEditable = false
        outputView.isSelectable = true
        outputView.font = TerminalStyle.mono
        outputView.textColor = NSColor(calibratedWhite: 0.95, alpha: 1)
        outputView.backgroundColor = NSColor(calibratedWhite: 0.035, alpha: 1)
        outputView.textContainerInset = NSSize(width: 16, height: 12)
        // 默认段落样式 + 输入属性都换成统一行高，否则每段 append 进来的文本
        // 会各自按自己的字体算行高，行距忽大忽小。
        outputView.defaultParagraphStyle = TerminalStyle.paragraph()
        outputView.typingAttributes = [
            .font: TerminalStyle.mono,
            .foregroundColor: NSColor(calibratedWhite: 0.95, alpha: 1),
            .paragraphStyle: TerminalStyle.paragraph(),
        ]
        // NSTextView 放进 NSScrollView 时必须显式声明「宽跟随、高自由」。
        // 不声明的话 textContainer 宽度可能是 0，文字会被挤成一列、互相重叠。
        outputView.minSize = NSSize(width: 0, height: 0)
        outputView.maxSize = NSSize(width: CGFloat.greatestFiniteMagnitude,
                                    height: CGFloat.greatestFiniteMagnitude)
        outputView.isVerticallyResizable = true
        outputView.isHorizontallyResizable = false
        outputView.autoresizingMask = [.width]
        outputView.textContainer?.lineFragmentPadding = 0
        outputView.textContainer?.widthTracksTextView = true
        outputView.string = ""

        let scrollView = NSScrollView()
        scrollView.documentView = outputView
        scrollView.hasVerticalScroller = true
        scrollView.borderType = .bezelBorder
        scrollView.translatesAutoresizingMaskIntoConstraints = false

        appendOutput("欢迎使用 CodeVigil Agent。\n")
        appendOutput("选择 Git 仓库以审查改动；使用 AI 前请在模型设置中填写 API 信息。\n\n")

        promptField.placeholderString = "输入问题，例如：分析这个仓库最近的改动"
        promptField.font = .systemFont(ofSize: 13)
        promptField.textColor = NSColor(calibratedWhite: 0.9, alpha: 1)
        promptField.backgroundColor = NSColor(calibratedWhite: 0.12, alpha: 1)
        promptField.isBezeled = true
        promptField.bezelStyle = .roundedBezel
        promptField.target = self
        promptField.action = #selector(sendPrompt)
        promptField.translatesAutoresizingMaskIntoConstraints = false

        sendButton = makeButton("发送", action: #selector(sendPrompt))
        cancelButton = makeButton("取消", action: #selector(cancelTask))
        cancelButton.isHidden = true
        newConversationButton = makeButton("新对话", action: #selector(newConversation))
        clearDisplayButton = makeButton("清空显示", action: #selector(clearDisplay))
        renameSessionButton = makeButton("重命名", action: #selector(renameConversation))
        deleteSessionButton = makeButton("删除", action: #selector(deleteConversation))
        exportSessionButton = makeButton("导出", action: #selector(exportConversation))
        newConversationButton.toolTip = "开始新的会话并清空当前显示；旧会话文件会保留"
        clearDisplayButton.toolTip = "只清空屏幕上的消息，不会清除当前会话上下文"
        let chatRow = NSStackView(views: [promptField, sendButton, cancelButton, clearDisplayButton])
        chatRow.orientation = .horizontal
        chatRow.alignment = .centerY
        chatRow.spacing = 10
        promptField.setContentCompressionResistancePriority(.defaultLow, for: .horizontal)

        historySearchField.placeholderString = "搜索标题和消息"
        historySearchField.target = self
        historySearchField.action = #selector(searchSessions)
        historySearchField.sendsSearchStringImmediately = true
        historyTableView.headerView = nil
        historyTableView.rowHeight = 70
        historyTableView.usesAlternatingRowBackgroundColors = true
        historyTableView.delegate = self
        historyTableView.dataSource = self
        let historyColumn = NSTableColumn(identifier: NSUserInterfaceItemIdentifier("history"))
        historyTableView.addTableColumn(historyColumn)
        let historyScroll = NSScrollView()
        historyScroll.documentView = historyTableView
        historyScroll.hasVerticalScroller = true
        historyScroll.borderType = .bezelBorder
        historyScroll.translatesAutoresizingMaskIntoConstraints = false
        let historyActions = NSStackView(views: [newConversationButton, renameSessionButton,
                                                 deleteSessionButton, exportSessionButton])
        historyActions.orientation = .horizontal
        historyActions.alignment = .centerY
        historyActions.spacing = 4
        [newConversationButton, renameSessionButton, deleteSessionButton, exportSessionButton].forEach {
            $0.font = .systemFont(ofSize: 11, weight: .medium)
        }
        let sidebarStack = NSStackView(views: [historySearchField, historyScroll, historyActions])
        sidebarStack.orientation = .vertical
        sidebarStack.alignment = .width
        sidebarStack.spacing = 9
        sidebarStack.translatesAutoresizingMaskIntoConstraints = false
        let sidebar = NSView()
        sidebar.translatesAutoresizingMaskIntoConstraints = false
        sidebar.addSubview(sidebarStack)
        NSLayoutConstraint.activate([
            sidebarStack.leadingAnchor.constraint(equalTo: sidebar.leadingAnchor, constant: 10),
            sidebarStack.trailingAnchor.constraint(equalTo: sidebar.trailingAnchor, constant: -10),
            sidebarStack.topAnchor.constraint(equalTo: sidebar.topAnchor, constant: 12),
            sidebarStack.bottomAnchor.constraint(equalTo: sidebar.bottomAnchor, constant: -12),
            historySearchField.heightAnchor.constraint(equalToConstant: 30),
        ])

        let mainStack = NSStackView(views: [header, repoRow, actionRow, scrollView, chatRow])
        mainStack.orientation = .vertical
        mainStack.alignment = .width
        mainStack.spacing = 14
        mainStack.translatesAutoresizingMaskIntoConstraints = false
        let mainPanel = NSView()
        mainPanel.translatesAutoresizingMaskIntoConstraints = false
        mainPanel.addSubview(mainStack)
        NSLayoutConstraint.activate([
            mainStack.leadingAnchor.constraint(equalTo: mainPanel.leadingAnchor, constant: 16),
            mainStack.trailingAnchor.constraint(equalTo: mainPanel.trailingAnchor, constant: -18),
            mainStack.topAnchor.constraint(equalTo: mainPanel.topAnchor, constant: 16),
            mainStack.bottomAnchor.constraint(equalTo: mainPanel.bottomAnchor, constant: -16),
            scrollView.heightAnchor.constraint(greaterThanOrEqualToConstant: 320),
            repositoryField.heightAnchor.constraint(equalToConstant: 30),
            promptField.heightAnchor.constraint(equalToConstant: 30),
        ])

        let splitView = NSSplitView()
        splitView.isVertical = true
        splitView.dividerStyle = .thin
        splitView.translatesAutoresizingMaskIntoConstraints = false
        splitView.addSubview(sidebar)
        splitView.addSubview(mainPanel)
        NSLayoutConstraint.activate([
            sidebar.widthAnchor.constraint(equalToConstant: 255),
        ])
        content.addSubview(splitView)
        NSLayoutConstraint.activate([
            splitView.leadingAnchor.constraint(equalTo: content.leadingAnchor),
            splitView.trailingAnchor.constraint(equalTo: content.trailingAnchor),
            splitView.topAnchor.constraint(equalTo: content.topAnchor),
            splitView.bottomAnchor.constraint(equalTo: content.bottomAnchor),
        ])

        window = NSWindow(
            contentRect: NSRect(x: 0, y: 0, width: 1080, height: 720),
            styleMask: [.titled, .closable, .miniaturizable, .resizable],
            backing: .buffered,
            defer: false
        )
        window.title = "CodeVigil Agent"
        window.minSize = NSSize(width: 760, height: 520)
        window.center()
        window.contentView = content
        window.appearance = NSAppearance(named: .darkAqua)
        window.delegate = self
    }

    private func makeButton(_ title: String, action: Selector) -> NSButton {
        let button = NSButton(title: title, target: self, action: action)
        button.bezelStyle = .rounded
        button.font = .systemFont(ofSize: 13, weight: .medium)
        button.contentTintColor = NSColor(calibratedRed: 0.48, green: 0.92, blue: 0.78, alpha: 1)
        return button
    }

    @objc private func chooseRepository() {
        let panel = NSOpenPanel()
        panel.title = "选择 Git 仓库"
        panel.prompt = "选择"
        panel.canChooseDirectories = true
        panel.canChooseFiles = false
        panel.allowsMultipleSelection = false
        panel.begin { [weak self] response in
            guard response == .OK, let url = panel.url else { return }
            self?.repositoryField.stringValue = url.path
            UserDefaults.standard.set(url.path, forKey: "lastRepositoryPath")
            self?.setStatus("已选择仓库")
        }
    }

    @objc private func reviewChanges() {
        runReview(offline: false)
    }

    @objc private func offlineReview() {
        runReview(offline: true)
    }

    @objc private func configureModel() {
        let configURL = modelConfigURL()
        let existing = (try? Data(contentsOf: configURL)).flatMap {
            (try? JSONSerialization.jsonObject(with: $0)) as? [String: Any]
        } ?? [:]
        // 清单只从 CLI 取（scripts/model_catalog.py 的 CATALOG），失败则降级手动输入
        let load = ModelCatalogLoader.load(pythonPath: pythonRuntimePath(),
                                           backend: backendRoot(),
                                           environment: backendEnvironment())
        if !load.error.isEmpty {
            appendOutput("\n无法读取模型清单：\(load.error)（已改为手动输入）\n", color: .systemOrange)
        }
        let form = ModelSettingsForm(existing: existing, load: load)
        let alert = NSAlert()
        alert.messageText = "模型设置"
        alert.accessoryView = form.grid
        alert.addButton(withTitle: "保存")
        alert.addButton(withTitle: "取消")
        var selection: (provider: String, model: String, baseURL: String)?
        while selection == nil {
            guard alert.runModal() == .alertFirstButtonReturn else { return }
            selection = form.selection()
            if selection == nil {
                // 不关窗口重来：用户填的 Key / base_url 还在，改一下就能存
                form.showHint(form.validationError ?? "模型不能为空：请在「模型」下拉里选一个。")
            }
        }
        guard let chosen = selection else { return }
        var config = existing
        config["provider"] = chosen.provider
        config["model"] = chosen.model
        config["base_url"] = chosen.baseURL
        if let label = form.selectedLabel() {
            // label 只是配置里的注释，同步一下，免得留着上一个厂商的名字
            config["label"] = label
        }
        if !form.keyField.stringValue.isEmpty {
            config["api_key"] = form.keyField.stringValue
        }
        do {
            try FileManager.default.createDirectory(at: configURL.deletingLastPathComponent(), withIntermediateDirectories: true, attributes: [.posixPermissions: 0o700])
            let data = try JSONSerialization.data(withJSONObject: config, options: [.prettyPrinted, .sortedKeys])
            try data.write(to: configURL, options: .atomic)
            try FileManager.default.setAttributes([.posixPermissions: 0o600], ofItemAtPath: configURL.path)
            if let model = validateModelConfiguration() {
                setStatus("配置已保存并可加载：\(model)")
            } else {
                setStatus("设置已保存；Python CLI 未能加载，请检查配置")
            }
        } catch {
            appendOutput("\n保存模型设置失败：\(error.localizedDescription)\n")
            setStatus("设置失败")
        }
    }

    @objc private func sendPrompt() {
        let prompt = promptField.stringValue.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !prompt.isEmpty, runningProcess == nil else { return }
        promptField.stringValue = ""
        let repository = repositoryField.stringValue.trimmingCharacters(in: .whitespacesAndNewlines)
        if repository != sessionRepository {
            sessionID = UUID().uuidString
            currentSessionName = nil
            currentTitle = "新对话"
            currentMessages = []
            sessionRepository = repository
        }
        let sessionName = currentSessionName ?? "desktop-\(sessionID)"
        currentSessionName = sessionName
        let repositoryPath = repository.isEmpty ? "" : URL(fileURLWithPath: repository).standardizedFileURL.path
        currentMessages.append(["role": "user", "content": prompt, "status": "running"])
        renderConversation()
        let arguments = ["chat", "--message", prompt, "--network", "auto",
                         "--session", sessionName, "--repository", repositoryPath, "--json"]
        runAgent(arguments: arguments, task: .chat(prompt, sessionName))
    }

    @objc private func newConversation() {
        guard runningProcess == nil else { return }
        sessionID = UUID().uuidString
        currentSessionName = nil
        currentTitle = "新对话"
        currentMessages = []
        sessionRepository = repositoryField.stringValue.trimmingCharacters(in: .whitespacesAndNewlines)
        suppressHistorySelection = true
        historyTableView.deselectAll(nil)
        suppressHistorySelection = false
        renderConversation()
        setStatus("新对话")
    }

    @objc private func searchSessions() {
        searchWorkItem?.cancel()
        let work = DispatchWorkItem { [weak self] in self?.refreshSessions() }
        searchWorkItem = work
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.25, execute: work)
    }

    @objc private func renameConversation() {
        guard let name = currentSessionName, runningProcess == nil else { return }
        let field = NSTextField(string: currentTitle)
        field.frame = NSRect(x: 0, y: 0, width: 320, height: 24)
        let alert = NSAlert()
        alert.messageText = "重命名对话"
        alert.accessoryView = field
        alert.addButton(withTitle: "保存")
        alert.addButton(withTitle: "取消")
        guard alert.runModal() == .alertFirstButtonReturn else { return }
        let title = field.stringValue.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !title.isEmpty else { setStatus("标题不能为空"); return }
        runAgent(arguments: ["sessions", "rename", name, title], task: .sessionRename(name, title))
    }

    @objc private func deleteConversation() {
        guard let name = currentSessionName, runningProcess == nil else { return }
        let alert = NSAlert()
        alert.messageText = "删除这条历史对话？"
        alert.informativeText = "对话记录会从本机移除，无法撤销。"
        alert.addButton(withTitle: "删除")
        alert.addButton(withTitle: "取消")
        guard alert.runModal() == .alertFirstButtonReturn else { return }
        runAgent(arguments: ["sessions", "delete", name], task: .sessionDelete(name))
    }

    @objc private func exportConversation() {
        guard let name = currentSessionName, runningProcess == nil else { return }
        let panel = NSSavePanel()
        panel.nameFieldStringValue = "\(safeFilename(currentTitle)).md"
        panel.allowedContentTypes = [.plainText]
        panel.begin { [weak self] response in
            guard response == .OK, let url = panel.url else { return }
            self?.runAgent(arguments: ["sessions", "export", name, "--output", url.path],
                           task: .sessionExport(name, url.path))
        }
    }

    private func safeFilename(_ text: String) -> String {
        let safe = text.replacingOccurrences(of: "[^A-Za-z0-9 _-]", with: "-", options: .regularExpression)
        return String((safe.trimmingCharacters(in: .whitespacesAndNewlines).prefix(64)))
    }

    private func modelConfigURL() -> URL {
        let environment = ProcessInfo.processInfo.environment
        if let configured = environment["REVIEWAGENT_CONFIG"], !configured.isEmpty {
            return URL(fileURLWithPath: (configured as NSString).expandingTildeInPath)
        }
        let root = environment["REVIEWAGENT_HOME"] ??
            URL(fileURLWithPath: NSHomeDirectory()).appendingPathComponent(".reviewagent").path
        return URL(fileURLWithPath: (root as NSString).expandingTildeInPath)
            .appendingPathComponent("ai_config.json")
    }

    /// 找本机 Python 3（macOS 上常见的几个安装位置）。
    private func pythonRuntimePath() -> String? {
        let candidates = ["/opt/homebrew/bin/python3", "/usr/local/bin/python3",
                          "\(NSHomeDirectory())/.local/bin/python3", "/usr/bin/python3"]
        return candidates.first { FileManager.default.isExecutableFile(atPath: $0) }
    }

    /// 调用后端 CLI 时统一的环境变量（路径与编码沿用现有实现）。
    private func backendEnvironment() -> [String: String] {
        var environment = ProcessInfo.processInfo.environment
        environment["PYTHONPATH"] = backendRoot().path + ":" + (environment["PYTHONPATH"] ?? "")
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        environment["REVIEWAGENT_HOME"] = environment["REVIEWAGENT_HOME"] ??
            URL(fileURLWithPath: NSHomeDirectory()).appendingPathComponent(".reviewagent").path
        environment["REVIEWAGENT_CONFIG"] = modelConfigURL().standardizedFileURL.path
        return environment
    }

    private func validateModelConfiguration() -> String? {
        guard let path = pythonRuntimePath() else { return nil }
        let process = Process()
        let output = Pipe()
        process.executableURL = URL(fileURLWithPath: path)
        process.currentDirectoryURL = backendRoot()
        process.arguments = ["-c", "from scripts.ai_adapter import get_ai_client; c=get_ai_client(); import json; print(json.dumps({'model': c.provider_name + '/' + c.model_name}))"]
        process.standardOutput = output
        process.standardError = FileHandle.nullDevice
        process.environment = backendEnvironment()
        do {
            try process.run()
            process.waitUntilExit()
            let data = output.fileHandleForReading.readDataToEndOfFile()
            guard process.terminationStatus == 0,
                  let payload = try? JSONSerialization.jsonObject(with: data) as? [String: String] else {
                return nil
            }
            return payload["model"]
        } catch {
            return nil
        }
    }

    private func refreshSessions(openCurrent: Bool = false) {
        if openCurrent { openSessionAfterRefresh = currentSessionName }
        var arguments = ["sessions", "list"]
        let query = historySearchField.stringValue.trimmingCharacters(in: .whitespacesAndNewlines)
        if !query.isEmpty { arguments += ["--query", query] }
        runAgent(arguments: arguments, task: .sessionsList(query))
    }

    private func openSession(_ name: String) {
        guard runningProcess == nil else { return }
        runAgent(arguments: ["sessions", "show", name], task: .sessionShow(name))
    }

    func numberOfRows(in tableView: NSTableView) -> Int { historyRows.count }

    func tableView(_ tableView: NSTableView, viewFor tableColumn: NSTableColumn?, row: Int) -> NSView? {
        guard historyRows.indices.contains(row) else { return nil }
        let identifier = NSUserInterfaceItemIdentifier("HistoryCell")
        let cell = (tableView.makeView(withIdentifier: identifier, owner: self) as? HistoryCell) ??
            HistoryCell(frame: .zero)
        cell.identifier = identifier
        cell.configure(historyRows[row])
        cell.setEmphasized(tableView.selectedRowIndexes.contains(row))
        return cell
    }

    func tableViewSelectionDidChange(_ notification: Notification) {
        guard let table = notification.object as? NSTableView else { return }
        // 仿 WorkBuddy：选中行标题深色，其余灰色（复用可见行的 cell，避免整表刷新）
        table.enumerateAvailableRowViews { rowView, row in
            (rowView.view(atColumn: 0) as? HistoryCell)?
                .setEmphasized(table.selectedRowIndexes.contains(row))
        }
        guard !suppressHistorySelection,
              historyRows.indices.contains(table.selectedRow) else { return }
        openSession(historyRows[table.selectedRow].name)
    }

    /// restoredAt 非空时在顶部追加「恢复时间」一行（打开历史会话时传入）。
    private func renderConversation(restoredAt: String? = nil) {
        outputView.string = ""
        appendOutput("\(currentTitle)\n", color: NSColor(calibratedRed: 0.48, green: 0.92, blue: 0.78, alpha: 1), bold: true)
        let repository = repositoryField.stringValue.trimmingCharacters(in: .whitespacesAndNewlines)
        appendOutput("仓库：\(repository.isEmpty ? "未关联" : repository)\n", color: .secondaryLabelColor)
        if let restoredAt = restoredAt, !restoredAt.isEmpty {
            appendOutput("恢复时间：\(restoredAt)\n", color: .secondaryLabelColor)
        }
        appendOutput("\n")
        for message in currentMessages {
            let role = message["role"] as? String ?? ""
            let content = message["content"] as? String ?? ""
            let state = message["status"] as? String ?? "completed"
            if role == "user" {
                appendOutput("你\n", color: NSColor(calibratedRed: 0.48, green: 0.92, blue: 0.78, alpha: 1), bold: true)
                appendOutput(content + "\n")
                switch state {
                case "running": appendOutput("Agent 正在生成…\n\n", color: .secondaryLabelColor)
                case "failed":
                    appendOutput("请求失败；未生成成功回复。\n", color: .systemRed, bold: true)
                    if let error = message["error"] as? String { appendOutput(error + "\n\n", color: .systemRed) }
                case "interrupted": appendOutput("请求中断；没有成功回复。\n\n", color: .systemOrange)
                default: appendOutput("\n")
                }
            } else if role == "assistant", state == "completed" {
                appendOutput("Agent\n", color: NSColor(calibratedRed: 0.48, green: 0.92, blue: 0.78, alpha: 1), bold: true)
                appendOutput(content + "\n\n")
            }
        }
        // 打开历史会话后自动滚到最新一条消息：先确保长文本排版完成再滚动，
        // 否则超长会话可能停在中间位置
        if let container = outputView.textContainer {
            outputView.layoutManager?.ensureLayout(for: container)
        }
        outputView.scrollRangeToVisible(NSRange(location: (outputView.string as NSString).length, length: 0))
    }

    @objc private func clearDisplay() {
        let alert = NSAlert()
        alert.messageText = "清空消息显示？"
        alert.informativeText = "只清空屏幕内容；当前会话上下文仍会用于后续提问。选择“新对话”才会开始空白会话。"
        alert.addButton(withTitle: "清空显示")
        alert.addButton(withTitle: "取消")
        guard alert.runModal() == .alertFirstButtonReturn else { return }
        outputView.string = ""
        setStatus("显示已清空；会话保留")
    }

    @objc private func cancelTask() {
        guard let process = runningProcess else { return }
        cancelRequested = true
        cancelButton.isEnabled = false
        setStatus("正在取消…")
        terminate(process)
    }

    private func runReview(offline: Bool) {
        let repoPath = repositoryField.stringValue.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !repoPath.isEmpty else {
            appendOutput("\n请选择一个 Git 仓库目录后再审查。\n", color: .systemRed)
            setStatus("缺少仓库目录")
            return
        }
        let repo = URL(fileURLWithPath: repoPath).standardizedFileURL
        var isDirectory: ObjCBool = false
        guard FileManager.default.fileExists(atPath: repo.path, isDirectory: &isDirectory),
              isDirectory.boolValue else {
            appendOutput("\n审查失败：目录不存在或不是文件夹：\(repo.path)\n", color: .systemRed)
            setStatus("仓库目录无效")
            return
        }
        let git = Process()
        git.executableURL = URL(fileURLWithPath: "/usr/bin/git")
        git.arguments = ["-C", repo.path, "rev-parse", "--show-toplevel"]
        git.standardOutput = FileHandle.nullDevice
        git.standardError = FileHandle.nullDevice
        do {
            try git.run()
            git.waitUntilExit()
        } catch {
            appendOutput("\n审查失败：无法启动 Git：\(error.localizedDescription)\n", color: .systemRed)
            setStatus("Git 不可用")
            return
        }
        guard git.terminationStatus == 0 else {
            appendOutput("\n审查失败：所选目录不是有效的 Git 仓库。\n", color: .systemRed)
            setStatus("不是 Git 仓库")
            return
        }
        UserDefaults.standard.set(repo.path, forKey: "lastRepositoryPath")
        var arguments = ["review"]
        if offline { arguments.append("--offline") }
        arguments.append("--json")
        runAgent(arguments: arguments, task: .review)
    }

    private func runAgent(arguments: [String], task: AgentTask) {
        guard runningProcess == nil else {
            setStatus("任务正在运行")
            return
        }

        let repo = repositoryField.stringValue.trimmingCharacters(in: .whitespacesAndNewlines)
        let sessionOperation: Bool
        switch task {
        case .sessionsList(_), .sessionShow(_), .sessionRename(_, _), .sessionDelete(_), .sessionExport(_, _):
            sessionOperation = true
        default:
            sessionOperation = false
        }
        let workingDirectory = sessionOperation || repo.isEmpty ? backendRoot() : URL(fileURLWithPath: repo)
        var isDirectory: ObjCBool = false
        guard FileManager.default.fileExists(atPath: workingDirectory.path, isDirectory: &isDirectory),
              isDirectory.boolValue else {
            appendOutput("\n找不到工作目录：\(workingDirectory.path)\n", color: .systemRed)
            setStatus("目录不存在")
            return
        }

        guard let pythonPath = pythonRuntimePath() else {
            appendOutput("\n找不到 Python 3。请先安装 Python 3.7+。\n", color: .systemRed)
            setStatus("缺少 Python")
            return
        }

        let process = Process()
        let stdoutPipe = Pipe()
        let stderrPipe = Pipe()
        let output = ProcessOutput()
        let readers = DispatchGroup()
        let taskID = UUID()
        process.executableURL = URL(fileURLWithPath: pythonPath)
        let cliPath = backendRoot().appendingPathComponent("ascend_cli.py").path
        process.arguments = ["-c", """
            import os, signal, subprocess, sys, time
            child = None
            stop_signal = 0
            def stop(signum, _frame):
                global stop_signal
                stop_signal = signum
                if child is not None:
                    try:
                        os.killpg(child.pid, signal.SIGTERM)
                        time.sleep(0.1)
                        try:
                            os.killpg(child.pid, signal.SIGKILL)
                        except ProcessLookupError:
                            pass
                    except (ProcessLookupError, ChildProcessError):
                        pass
            signal.signal(signal.SIGTERM, stop)
            signal.pthread_sigmask(signal.SIG_BLOCK, {signal.SIGTERM})
            try:
                child = subprocess.Popen([sys.executable] + sys.argv[1:], start_new_session=True)
            finally:
                signal.pthread_sigmask(signal.SIG_UNBLOCK, {signal.SIGTERM})
            status = child.wait()
            sys.exit(128 + stop_signal if stop_signal else status)
            """, cliPath] + arguments
        process.currentDirectoryURL = workingDirectory
        process.standardOutput = stdoutPipe
        process.standardError = stderrPipe
        process.environment = backendEnvironment()

        switch task {
        case .chat:
            // 用户消息已在 sendPrompt 里随 renderConversation 渲染过一次，
            // 这里再追加会出现两条「你 + 提问」，所以不再重复输出
            break
        case .review, .sessionsList(_), .sessionShow(_), .sessionRename(_, _), .sessionDelete(_), .sessionExport(_, _):
            if case .review = task {
                appendOutput(offlineReviewHeading(arguments) + "\n", color: NSColor(calibratedRed: 0.48, green: 0.92, blue: 0.78, alpha: 1), bold: true)
            }
        }
        setStatus("运行中…")
        runningProcess = process
        runningPipes = [stdoutPipe, stderrPipe]
        runningReaders = readers
        let stdoutCompletion = ReaderCompletion(readers)
        let stderrCompletion = ReaderCompletion(readers)
        runningReaderCompletions = [stdoutCompletion, stderrCompletion]
        activeTaskID = taskID
        cancelRequested = false
        setControlsRunning(true)
        readers.enter()
        stdoutPipe.fileHandleForReading.readabilityHandler = { handle in
            let data = handle.availableData
            if data.isEmpty {
                handle.readabilityHandler = nil
                stdoutCompletion.finish()
            }
            else { output.append(data, isError: false) }
        }
        readers.enter()
        stderrPipe.fileHandleForReading.readabilityHandler = { handle in
            let data = handle.availableData
            if data.isEmpty {
                handle.readabilityHandler = nil
                stderrCompletion.finish()
            }
            else { output.append(data, isError: true) }
        }
        process.terminationHandler = { [weak self] terminatedProcess in
            guard let self else { return }
            DispatchQueue.global().async {
                let readersFinished = readers.wait(timeout: .now() + 5) == .success
                if !readersFinished {
                    [stdoutPipe, stderrPipe].forEach { pipe in
                        pipe.fileHandleForReading.readabilityHandler = nil
                        try? pipe.fileHandleForReading.close()
                    }
                    stdoutCompletion.finish()
                    stderrCompletion.finish()
                }
                DispatchQueue.main.async {
                    guard self.activeTaskID == taskID else { return }
                    let (stdout, stderr) = output.values()
                    try? stdoutPipe.fileHandleForReading.close()
                    try? stderrPipe.fileHandleForReading.close()
                    self.runningProcess = nil
                    self.runningPipes = []
                    self.runningReaders = nil
                    self.runningReaderCompletions = []
                    self.activeTaskID = nil
                    self.setControlsRunning(false)
                    if self.cancelRequested {
                        if case .chat = task {
                            if let index = self.currentMessages.lastIndex(where: {
                                $0["role"] as? String == "user" && $0["status"] as? String == "running"
                            }) {
                                self.currentMessages[index]["status"] = "interrupted"
                            }
                            self.renderConversation()
                            self.statusAfterHistoryRefresh = "已取消"
                            self.refreshSessions()
                        } else {
                            self.appendOutput("\n任务已取消。\n", color: .systemOrange)
                            self.setStatus("已取消")
                        }
                    } else {
                        self.finishTask(task, status: readersFinished ? terminatedProcess.terminationStatus : -1,
                                        stdout: stdout, stderr: stderr)
                    }
                }
            }
        }

        do {
            try process.run()
        } catch {
            runningProcess = nil
            runningReaderCompletions.forEach { $0.finish() }
            runningReaderCompletions = []
            [stdoutPipe, stderrPipe].forEach { pipe in
                pipe.fileHandleForReading.readabilityHandler = nil
                try? pipe.fileHandleForReading.close()
            }
            runningPipes = []
            runningReaders = nil
            activeTaskID = nil
            setControlsRunning(false)
            appendOutput("\n启动失败：\(error.localizedDescription)\n", color: .systemRed)
            setStatus("启动失败")
        }
    }

    private func backendRoot() -> URL {
        Bundle.main.resourceURL?.appendingPathComponent("backend") ??
            URL(fileURLWithPath: FileManager.default.currentDirectoryPath)
    }

    private func finishTask(_ task: AgentTask, status: Int32, stdout: Data, stderr: Data) {
        switch task {
        case .chat(_, let name):
            guard let payload = try? JSONSerialization.jsonObject(with: stdout) as? [String: Any] else {
                appendOutput("请求失败：CLI 返回无效 JSON。\n\(safeDiagnostic(stderr))\n", color: .systemRed)
                setStatus("请求失败")
                openSessionAfterRefresh = name
                refreshSessions()
                return
            }
            guard status == 0, payload["ok"] as? Bool == true else {
                appendOutput("Agent 请求失败：\(payload["error"] as? String ?? "CLI 以退出码 \(status) 结束。")\n",
                             color: .systemRed)
                setStatus("请求失败")
                openSessionAfterRefresh = name
                refreshSessions()
                return
            }
            guard payload["reply"] as? String != nil else {
                appendOutput("请求失败：JSON 响应缺少 Agent 回复。\n", color: .systemRed)
                setStatus("请求失败")
                openSessionAfterRefresh = name
                refreshSessions()
                return
            }
            openSessionAfterRefresh = name
            refreshSessions()
        case .review:
            renderReview(status: status, stdout: stdout, stderr: stderr)
        case .sessionsList:
            guard status == 0,
                  let payload = try? JSONSerialization.jsonObject(with: stdout) as? [String: Any],
                  payload["ok"] as? Bool == true,
                  let sessions = payload["sessions"] as? [[String: Any]] else {
                setStatus("历史读取失败")
                return
            }
            // 跳过两类噪音，避免点开必然是空壳或必然报错：
            //   ① 损坏文件——CLI 降级成空壳行（标题退化为文件名、无时间/轮次/预览）
            //   ② 空会话——终端退出时 CLI 会自动保存一份 0 轮无内容的会话
            historyRows = sessions.map(HistoryRow.init).filter { row in
                !(row.turns == 0 && row.summary.isEmpty)
            }
            historyTableView.reloadData()
            // 刷新后把选中行恢复到正在查看的会话（不重新拉取内容，避免覆盖当前显示）
            if let current = currentSessionName,
               let row = historyRows.firstIndex(where: { $0.name == current }),
               historyTableView.selectedRow != row {
                suppressHistorySelection = true
                historyTableView.selectRowIndexes(IndexSet(integer: row), byExtendingSelection: false)
                suppressHistorySelection = false
            }
            if let name = openSessionAfterRefresh {
                openSessionAfterRefresh = nil
                openSession(name)
            } else {
                setStatus(statusAfterHistoryRefresh ?? "历史已更新")
                statusAfterHistoryRefresh = nil
            }
        case .sessionShow(let requestedName):
            let parsed = (try? JSONSerialization.jsonObject(with: stdout)) as? [String: Any]
            guard status == 0, let payload = parsed,
                  payload["ok"] as? Bool == true,
                  let session = payload["session"] as? [String: Any],
                  let name = session["name"] as? String,
                  let messages = session["messages"] as? [[String: Any]] else {
                // 打开失败：给出明确原因（CLI 错误信息优先，其次 stderr 诊断），不崩溃；
                // 列表与正在显示的会话内容都不动，只把选中行回退到当前会话
                let reason = (parsed?["error"] as? String) ?? safeDiagnostic(stderr)
                appendOutput("\n无法恢复对话「\(requestedName)」：\(reason)\n", color: .systemRed)
                setStatus("历史恢复失败")
                suppressHistorySelection = true
                if let current = currentSessionName,
                   let row = historyRows.firstIndex(where: { $0.name == current }) {
                    historyTableView.selectRowIndexes(IndexSet(integer: row), byExtendingSelection: false)
                } else {
                    historyTableView.deselectAll(nil)
                }
                suppressHistorySelection = false
                return
            }
            currentSessionName = name
            currentTitle = session["title"] as? String ?? name
            currentMessages = messages
            let repository = session["repository"] as? String ?? ""
            repositoryField.stringValue = repository
            sessionRepository = repository
            if !repository.isEmpty { UserDefaults.standard.set(repository, forKey: "lastRepositoryPath") }
            if name.hasPrefix("desktop-") { sessionID = String(name.dropFirst("desktop-".count)) }
            let formatter = DateFormatter()
            formatter.dateFormat = "yyyy-MM-dd HH:mm"
            renderConversation(restoredAt: formatter.string(from: Date()))
            suppressHistorySelection = true
            if let row = historyRows.firstIndex(where: { $0.name == name }) {
                historyTableView.selectRowIndexes(IndexSet(integer: row), byExtendingSelection: false)
            } else {
                historyTableView.deselectAll(nil)
            }
            suppressHistorySelection = false
            setStatus("已恢复对话")
            setControlsRunning(false)
        case .sessionRename(_, let title):
            guard let payload = try? JSONSerialization.jsonObject(with: stdout) as? [String: Any],
                  payload["ok"] as? Bool == true else {
                setStatus("重命名失败")
                return
            }
            currentTitle = title
            openSessionAfterRefresh = currentSessionName
            refreshSessions()
        case .sessionDelete(let name):
            guard let payload = try? JSONSerialization.jsonObject(with: stdout) as? [String: Any],
                  payload["ok"] as? Bool == true else {
                setStatus("删除失败")
                return
            }
            if currentSessionName == name {
                currentSessionName = nil
                currentTitle = "新对话"
                currentMessages = []
                sessionID = UUID().uuidString
                sessionRepository = repositoryField.stringValue
                renderConversation()
            }
            refreshSessions()
            setStatus("历史已删除")
        case .sessionExport(_, let path):
            guard let payload = try? JSONSerialization.jsonObject(with: stdout) as? [String: Any],
                  payload["ok"] as? Bool == true else {
                setStatus("导出失败")
                return
            }
            setStatus("已导出：\(path)")
        }
    }

    private func renderReview(status: Int32, stdout: Data, stderr: Data) {
        guard let payload = try? JSONSerialization.jsonObject(with: stdout) as? [String: Any] else {
            appendOutput("审查失败：CLI 返回无效 JSON；结果未作为通过处理。\n\(safeDiagnostic(stderr))\n",
                         color: .systemRed)
            setStatus("审查失败")
            return
        }
        let state = payload["status"] as? String
        if state == "no_changes" {
            guard status == 0,
                  let result = payload["review_result"] as? [String: Any],
                  let issues = result["issues"] as? [[String: Any]], issues.isEmpty,
                  let assessment = result["overall_assessment"] as? String,
                  !assessment.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
                  result["coverage"] as? String == "full",
                  let knowledge = payload["knowledge_retrieval"] as? [String: Any],
                  knowledge["references"] as? [Any] != nil,
                  knowledge["warnings"] as? [String] != nil,
                  let metadata = payload["metadata"] as? [String: Any],
                  let files = metadata["changed_files"] as? [String],
                  let message = payload["message"] as? String,
                  !message.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
                appendOutput("审查失败：空 diff 报告缺少有效字段；结果未作为通过处理。\n",
                             color: .systemRed)
                setStatus("报告不完整")
                return
            }
            appendOutput("没有可审查的改动。\n", color: .secondaryLabelColor)
            appendOutput("覆盖范围：\(files.count) 个文件；本次未执行审查。\n")
            appendOutput("知识库提示：本次未执行审查，未检索知识库。\n\n")
            setStatus("无可审查改动")
            return
        }
        if status != 0 || state == "error" || state == "needs_context" {
            let reviewResult = payload["review_result"] as? [String: Any]
            let reason = payload["error"] as? String ?? payload["question"] as? String ??
                reviewResult?["error"] as? String ??
                "CLI 以退出码 \(status) 结束。"
            appendOutput("审查失败：\(reason)\n结果未作为通过处理。\n", color: .systemRed)
            setStatus("审查失败")
            return
        }
        guard state == "complete" else {
            appendOutput("审查失败：报告缺少有效的 complete 状态；结果未作为通过处理。\n", color: .systemRed)
            setStatus("报告不完整")
            return
        }
        guard let result = payload["review_result"] as? [String: Any],
              let issues = result["issues"] as? [[String: Any]],
              result["error"] == nil else {
            appendOutput("审查失败：报告缺少有效的 review_result/issues，不能判定为通过。\n", color: .systemRed)
            setStatus("报告不完整")
            return
        }

        guard let assessment = result["overall_assessment"] as? String,
              !assessment.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
              let recommendation = result["recommendation"] as? String,
              ["approve", "request_changes", "comment"].contains(recommendation),
              let coverage = result["coverage"] as? String,
              ["full", "partial"].contains(coverage),
              let knowledge = payload["knowledge_retrieval"] as? [String: Any],
              let references = knowledge["references"] as? [Any],
              let warnings = knowledge["warnings"] as? [String],
              let metadata = payload["metadata"] as? [String: Any],
              let repository = metadata["repository"] as? [String: Any],
              let files = repository["changed_files"] as? [String] else {
            appendOutput("审查失败：报告缺少有效结论、覆盖范围或知识库字段；结果未作为通过处理。\n",
                         color: .systemRed)
            setStatus("报告不完整")
            return
        }

        appendOutput("总体结论：\(assessment)\n", bold: true)
        appendOutput("审查建议：\(recommendation)\n")
        appendOutput("覆盖范围：\(coverage)")
        if let note = result["coverage_note"] as? String, !note.isEmpty {
            appendOutput("；\(note)")
        }
        appendOutput("（\(files.count) 个文件）")
        appendOutput("\n")

        appendOutput("知识库提示：本地索引匹配 \(references.count) 条。\n")
        for warning in warnings { appendOutput("  · \(warning)\n", color: .secondaryLabelColor) }
        if let specialist = payload["specialist_context"] as? [String: Any] {
            let scenario = specialist["scenario"] as? String ?? "通用"
            let specialistState = specialist["status"] as? String ?? "未提供"
            appendOutput("专业覆盖：\(scenario)（\(specialistState)）\n")
        }

        if issues.isEmpty {
            appendOutput("\n未发现问题。\n", color: NSColor(calibratedRed: 0.48, green: 0.92, blue: 0.78, alpha: 1), bold: true)
        } else {
            appendOutput("\n发现 \(issues.count) 个问题\n", bold: true)
            for (index, issue) in issues.enumerated() {
                let severity = issue["severity"] as? String ?? "未标记"
                let title = issue["title"] as? String ?? issue["type"] as? String ?? "未提供标题"
                let color: NSColor = ["critical", "high"].contains(severity.lowercased()) ? .systemRed :
                    severity.lowercased() == "medium" ? .systemOrange : .systemYellow
                appendOutput("\(index + 1). [\(severity.uppercased())] \(title)\n", color: color, bold: true)
                appendOutput("位置：\(issue["location"] as? String ?? "未提供")\n", color: .secondaryLabelColor)
                appendOutput("说明：\(issue["description"] as? String ?? "报告未提供说明")\n")
                appendOutput("修复建议：\(issue["suggestion"] as? String ?? "报告未提供修复建议")\n\n")
            }
        }
        appendOutput("\n")
        setStatus("完成")
    }

    private func offlineReviewHeading(_ arguments: [String]) -> String {
        arguments.contains("--offline") ? "离线代码审查" : "审查当前改动"
    }

    private func safeDiagnostic(_ data: Data) -> String {
        var detail = String(decoding: data, as: UTF8.self).trimmingCharacters(in: .whitespacesAndNewlines)
        let environment = ProcessInfo.processInfo.environment
        var secrets = ["AI_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY"].compactMap { environment[$0] }
        if let config = try? Data(contentsOf: modelConfigURL()),
           let object = try? JSONSerialization.jsonObject(with: config) as? [String: Any],
           let key = object["api_key"] as? String {
            secrets.append(key)
        }
        for secret in secrets where secret.count >= 8 {
            detail = detail.replacingOccurrences(of: secret, with: "[API Key 已隐藏]")
        }
        if detail.isEmpty { return "CLI 没有提供错误详情。" }
        return String(detail.prefix(1000))
    }

    private func setControlsRunning(_ running: Bool) {
        sendButton.isEnabled = !running
        promptField.isEnabled = !running
        actionButtons.forEach { $0.isEnabled = !running }
        newConversationButton.isEnabled = !running
        clearDisplayButton.isEnabled = !running
        historySearchField.isEnabled = !running
        historyTableView.isEnabled = !running
        renameSessionButton.isEnabled = !running && currentSessionName != nil
        deleteSessionButton.isEnabled = !running && currentSessionName != nil
        exportSessionButton.isEnabled = !running && currentSessionName != nil
        cancelButton.isHidden = !running
        cancelButton.isEnabled = running
    }

    private func terminate(_ process: Process) {
        process.terminate()
        DispatchQueue.global().asyncAfter(deadline: .now() + 2) {
            if process.isRunning { Darwin.kill(process.processIdentifier, SIGKILL) }
        }
    }

    private func stopProcessForTermination() {
        guard let process = runningProcess else { return }
        activeTaskID = nil
        process.terminate()
        let deadline = Date().addingTimeInterval(3)
        while process.isRunning && Date() < deadline {
            Thread.sleep(forTimeInterval: 0.05)
        }
        if process.isRunning { Darwin.kill(process.processIdentifier, SIGKILL) }
        process.waitUntilExit()
        process.terminationHandler = nil
        runningPipes.forEach { pipe in
            pipe.fileHandleForReading.readabilityHandler = nil
            try? pipe.fileHandleForReading.close()
        }
        runningReaderCompletions.forEach { $0.finish() }
        runningReaderCompletions = []
        runningReaders?.wait()
        runningReaders = nil
        runningPipes = []
        runningProcess = nil
    }

    private func appendOutput(_ text: String, color: NSColor? = nil, bold: Bool = false) {
        guard let storage = outputView.textStorage else { return }
        let ink = color ?? outputView.textColor ?? NSColor.white
        storage.append(TerminalStyle.attributed(text, color: ink, bold: bold))
        outputView.scrollToEndOfDocument(nil)
    }

    private func setStatus(_ text: String) {
        statusLabel.stringValue = text
    }
}

let application = NSApplication.shared
let delegate = CodeVigilAgentDelegate()
application.delegate = delegate
application.setActivationPolicy(.regular)
application.run()
