//
//  MenuBarSettings.swift
//  Quotio
//
//  Menu bar quota display settings with persistence
//

import Foundation
import SwiftUI

// MARK: - Menu Bar Quota Item

/// Represents a single item selected for menu bar display
struct MenuBarQuotaItem: Codable, Identifiable, Hashable {
    let provider: String      // AIProvider.rawValue
    let accountKey: String    // email or account identifier
    
    var id: String { "\(provider)_\(accountKey)" }
    
    /// Get the AIProvider enum value
    var aiProvider: AIProvider? {
        // Handle "copilot" alias
        if provider == "copilot" {
            return .copilot
        }
        return AIProvider(rawValue: provider)
    }
    
    /// Short display symbol for the provider
    var providerSymbol: String {
        aiProvider?.menuBarSymbol ?? "?"
    }
}

// MARK: - Color Mode

/// Color mode for menu bar quota display
enum MenuBarColorMode: String, Codable, CaseIterable, Identifiable {
    case colored = "colored"       // Green/Yellow/Red based on quota %
    case monochrome = "monochrome" // White/Gray only
    
    var id: String { rawValue }
    
    var localizationKey: String {
        switch self {
        case .colored: return "settings.menubar.colored"
        case .monochrome: return "settings.menubar.monochrome"
        }
    }
}

// MARK: - Quota Display Mode

/// Display mode for quota percentage (used vs remaining)
enum QuotaDisplayMode: String, Codable, CaseIterable, Identifiable {
    case used = "used"           // Show percentage used (e.g., "75% used")
    case remaining = "remaining" // Show percentage remaining (e.g., "25% left")
    
    var id: String { rawValue }
    
    var localizationKey: String {
        switch self {
        case .used: return "settings.quota.displayMode.used"
        case .remaining: return "settings.quota.displayMode.remaining"
        }
    }
    
    /// Convert a remaining percentage to the display value based on mode
    func displayValue(from remainingPercent: Double) -> Double {
        switch self {
        case .used: return 100 - remainingPercent
        case .remaining: return remainingPercent
        }
    }
    
    var suffixKey: String {
        switch self {
        case .used: return "settings.quota.used"
        case .remaining: return "settings.quota.left"
        }
    }
}

// MARK: - Menu Bar Quota Display Item

/// Data for displaying a single quota item in menu bar
struct MenuBarQuotaDisplayItem: Identifiable {
    let id: String
    let providerSymbol: String
    let accountShort: String
    let percentage: Double
    let provider: AIProvider
    
    var statusColor: Color {
        if percentage > 50 { return .green }
        if percentage > 20 { return .orange }
        return .red
    }
}

// MARK: - Settings Manager

/// Manager for menu bar display settings with persistence
@MainActor
@Observable
final class MenuBarSettingsManager {
    static let shared = MenuBarSettingsManager()
    
    private let defaults = UserDefaults.standard
    private let selectedItemsKey = "menuBarSelectedQuotaItems"
    private let colorModeKey = "menuBarColorMode"
    private let showMenuBarIconKey = "showMenuBarIcon"
    private let showQuotaKey = "menuBarShowQuota"
    private let quotaDisplayModeKey = "quotaDisplayMode"
    
    /// Whether to show menu bar icon at all
    var showMenuBarIcon: Bool {
        didSet { defaults.set(showMenuBarIcon, forKey: showMenuBarIconKey) }
    }
    
    /// Whether to show quota in menu bar (only effective when showMenuBarIcon is true)
    var showQuotaInMenuBar: Bool {
        didSet { defaults.set(showQuotaInMenuBar, forKey: showQuotaKey) }
    }
    
    /// Selected items to display
    var selectedItems: [MenuBarQuotaItem] {
        didSet { saveSelectedItems() }
    }
    
    /// Color mode (colored vs monochrome)
    var colorMode: MenuBarColorMode {
        didSet { defaults.set(colorMode.rawValue, forKey: colorModeKey) }
    }
    
    /// Quota display mode (used vs remaining)
    var quotaDisplayMode: QuotaDisplayMode {
        didSet { defaults.set(quotaDisplayMode.rawValue, forKey: quotaDisplayModeKey) }
    }
    
    /// Threshold for warning when adding more items
    let warningThreshold = 3
    
    /// Check if adding another item would exceed the warning threshold
    var shouldWarnOnAdd: Bool {
        selectedItems.count >= warningThreshold
    }
    
    private init() {
        // Show menu bar icon - default true if not set
        if defaults.object(forKey: showMenuBarIconKey) == nil {
            defaults.set(true, forKey: showMenuBarIconKey)
        }
        self.showMenuBarIcon = defaults.bool(forKey: showMenuBarIconKey)
        
        // Show quota in menu bar - default true if not set
        if defaults.object(forKey: showQuotaKey) == nil {
            defaults.set(true, forKey: showQuotaKey)
        }
        self.showQuotaInMenuBar = defaults.bool(forKey: showQuotaKey)
        
        self.colorMode = MenuBarColorMode(rawValue: defaults.string(forKey: colorModeKey) ?? "") ?? .colored
        self.quotaDisplayMode = QuotaDisplayMode(rawValue: defaults.string(forKey: quotaDisplayModeKey) ?? "") ?? .used
        self.selectedItems = Self.loadSelectedItems(from: defaults, key: selectedItemsKey)
    }
    
    private func saveSelectedItems() {
        if let data = try? JSONEncoder().encode(selectedItems) {
            defaults.set(data, forKey: selectedItemsKey)
        }
    }
    
    private static func loadSelectedItems(from defaults: UserDefaults, key: String) -> [MenuBarQuotaItem] {
        guard let data = defaults.data(forKey: key),
              let items = try? JSONDecoder().decode([MenuBarQuotaItem].self, from: data) else {
            return []
        }
        return items
    }
    
    func addItem(_ item: MenuBarQuotaItem) {
        guard !selectedItems.contains(item) else { return }
        if !showQuotaInMenuBar {
            showQuotaInMenuBar = true
        }
        if !showMenuBarIcon {
            showMenuBarIcon = true
        }
        selectedItems.append(item)
    }
    
    /// Remove an item
    func removeItem(_ item: MenuBarQuotaItem) {
        selectedItems.removeAll { $0.id == item.id }
    }
    
    /// Check if item is selected
    func isSelected(_ item: MenuBarQuotaItem) -> Bool {
        selectedItems.contains(item)
    }
    
    /// Toggle item selection
    func toggleItem(_ item: MenuBarQuotaItem) {
        if isSelected(item) {
            removeItem(item)
        } else {
            addItem(item)
        }
    }
    
    /// Remove items that no longer exist in quota data
    func pruneInvalidItems(validItems: [MenuBarQuotaItem]) {
        let validIds = Set(validItems.map(\.id))
        selectedItems.removeAll { !validIds.contains($0.id) }
    }
    
    func autoSelectNewAccounts(availableItems: [MenuBarQuotaItem]) {
        let existingIds = Set(selectedItems.map(\.id))
        let newItems = availableItems.filter { !existingIds.contains($0.id) }
        
        let remainingSlots = warningThreshold - selectedItems.count
        if remainingSlots > 0 {
            let itemsToAdd = Array(newItems.prefix(remainingSlots))
            selectedItems.append(contentsOf: itemsToAdd)
        }
    }
}
