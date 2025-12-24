//
//  QuotaViewModel.swift
//  Quotio - CLIProxyAPI GUI Wrapper
//

import Foundation
import SwiftUI
import AppKit

@MainActor
@Observable
final class QuotaViewModel {
    let proxyManager: CLIProxyManager
    private var apiClient: ManagementAPIClient?
    private let antigravityFetcher = AntigravityQuotaFetcher()
    private let openAIFetcher = OpenAIQuotaFetcher()
    
    var currentPage: NavigationPage = .dashboard
    var authFiles: [AuthFile] = []
    var usageStats: UsageStats?
    var logs: [LogEntry] = []
    var isLoading = false
    var isLoadingQuotas = false
    var errorMessage: String?
    var oauthState: OAuthState?
    
    /// Quota data per provider per account (email -> QuotaData)
    var providerQuotas: [AIProvider: [String: ProviderQuotaData]] = [:]
    
    /// Subscription info per account (email -> SubscriptionInfo)
    var subscriptionInfos: [String: SubscriptionInfo] = [:]
    
    private var refreshTask: Task<Void, Never>?
    private var lastLogTimestamp: Int?
    
    init() {
        self.proxyManager = CLIProxyManager()
    }
    
    var authFilesByProvider: [AIProvider: [AuthFile]] {
        var result: [AIProvider: [AuthFile]] = [:]
        for file in authFiles {
            if let provider = file.providerType {
                result[provider, default: []].append(file)
            }
        }
        return result
    }
    
    var connectedProviders: [AIProvider] {
        Array(Set(authFiles.compactMap { $0.providerType })).sorted { $0.displayName < $1.displayName }
    }
    
    var disconnectedProviders: [AIProvider] {
        AIProvider.allCases.filter { provider in
            !connectedProviders.contains(provider)
        }
    }
    
    var totalAccounts: Int { authFiles.count }
    var readyAccounts: Int { authFiles.filter { $0.isReady }.count }
    
    func startProxy() async {
        do {
            try await proxyManager.start()
            setupAPIClient()
            startAutoRefresh()
            await refreshData()
        } catch {
            errorMessage = error.localizedDescription
        }
    }
    
    func stopProxy() {
        refreshTask?.cancel()
        refreshTask = nil
        proxyManager.stop()
        apiClient = nil
    }
    
    func toggleProxy() async {
        if proxyManager.proxyStatus.running {
            stopProxy()
        } else {
            await startProxy()
        }
    }
    
    private func setupAPIClient() {
        apiClient = ManagementAPIClient(
            baseURL: proxyManager.managementURL,
            authKey: proxyManager.managementKey
        )
    }
    
    private func startAutoRefresh() {
        refreshTask?.cancel()
        refreshTask = Task {
            while !Task.isCancelled {
                try? await Task.sleep(nanoseconds: 5_000_000_000)
                await refreshData()
            }
        }
    }
    
    private var lastQuotaRefresh: Date?
    private let quotaRefreshInterval: TimeInterval = 60
    
    func refreshData() async {
        guard let client = apiClient else { return }
        
        do {
            async let files = client.fetchAuthFiles()
            async let stats = client.fetchUsageStats()
            
            self.authFiles = try await files
            self.usageStats = try await stats
            
            let shouldRefreshQuotas = lastQuotaRefresh == nil || 
                Date().timeIntervalSince(lastQuotaRefresh!) >= quotaRefreshInterval
            
            if shouldRefreshQuotas && !isLoadingQuotas {
                Task {
                    await refreshAllQuotas()
                }
            }
        } catch {
            if !Task.isCancelled {
                errorMessage = error.localizedDescription
            }
        }
    }
    
    func refreshAllQuotas() async {
        guard !isLoadingQuotas else { return }
        
        isLoadingQuotas = true
        lastQuotaRefresh = Date()
        
        async let antigravity: () = refreshAntigravityQuotasInternal()
        async let openai: () = refreshOpenAIQuotasInternal()
        
        _ = await (antigravity, openai)
        
        isLoadingQuotas = false
    }
    
    private func refreshAntigravityQuotasInternal() async {
        let quotas = await antigravityFetcher.fetchAllAntigravityQuotas()
        providerQuotas[.antigravity] = quotas
        
        let subscriptions = await antigravityFetcher.fetchAllSubscriptionInfo()
        subscriptionInfos = subscriptions
    }
    
    private func refreshOpenAIQuotasInternal() async {
        let quotas = await openAIFetcher.fetchAllCodexQuotas()
        providerQuotas[.codex] = quotas
    }
    
    func refreshAntigravityQuotas() async {
        isLoadingQuotas = true
        
        let quotas = await antigravityFetcher.fetchAllAntigravityQuotas()
        providerQuotas[.antigravity] = quotas
        
        let subscriptions = await antigravityFetcher.fetchAllSubscriptionInfo()
        subscriptionInfos = subscriptions
        
        isLoadingQuotas = false
    }
    
    func refreshOpenAIQuotas() async {
        let quotas = await openAIFetcher.fetchAllCodexQuotas()
        providerQuotas[.codex] = quotas
    }
    
    func getQuotaForAccount(provider: AIProvider, email: String) -> ProviderQuotaData? {
        return providerQuotas[provider]?[email]
    }
    
    func refreshLogs() async {
        guard let client = apiClient else { return }
        
        do {
            let response = try await client.fetchLogs(after: lastLogTimestamp)
            if let lines = response.lines {
                let newEntries: [LogEntry] = lines.map { line in
                    let level: LogEntry.LogLevel
                    if line.contains("error") || line.contains("ERROR") {
                        level = .error
                    } else if line.contains("warn") || line.contains("WARN") {
                        level = .warn
                    } else if line.contains("debug") || line.contains("DEBUG") {
                        level = .debug
                    } else {
                        level = .info
                    }
                    return LogEntry(timestamp: Date(), level: level, message: line)
                }
                logs.append(contentsOf: newEntries)
                if logs.count > 500 {
                    logs = Array(logs.suffix(500))
                }
            }
            lastLogTimestamp = response.latestTimestamp
        } catch {
            // Silently ignore log fetch errors
        }
    }
    
    func startOAuth(for provider: AIProvider, projectId: String? = nil) async {
        guard let client = apiClient else {
            errorMessage = "Proxy not running"
            return
        }
        
        oauthState = OAuthState(provider: provider, status: .waiting)
        
        do {
            let response = try await client.getOAuthURL(for: provider, projectId: projectId)
            
            guard response.status == "ok", let urlString = response.url, let state = response.state else {
                oauthState = OAuthState(provider: provider, status: .error, error: response.error)
                return
            }
            
            if let url = URL(string: urlString) {
                NSWorkspace.shared.open(url)
            }
            
            oauthState = OAuthState(provider: provider, status: .polling, state: state)
            await pollOAuthStatus(state: state, provider: provider)
            
        } catch {
            oauthState = OAuthState(provider: provider, status: .error, error: error.localizedDescription)
        }
    }
    
    private func pollOAuthStatus(state: String, provider: AIProvider) async {
        guard let client = apiClient else { return }
        
        for _ in 0..<60 {
            try? await Task.sleep(nanoseconds: 2_000_000_000)
            
            do {
                let response = try await client.pollOAuthStatus(state: state)
                
                switch response.status {
                case "ok":
                    oauthState = OAuthState(provider: provider, status: .success)
                    await refreshData()
                    return
                case "error":
                    oauthState = OAuthState(provider: provider, status: .error, error: response.error)
                    return
                default:
                    continue
                }
            } catch {
                continue
            }
        }
        
        oauthState = OAuthState(provider: provider, status: .error, error: "OAuth timeout")
    }
    
    func deleteAuthFile(_ file: AuthFile) async {
        guard let client = apiClient else { return }
        
        do {
            try await client.deleteAuthFile(name: file.name)
            await refreshData()
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func importVertexServiceAccount(url: URL) async {
        guard let client = apiClient else {
            errorMessage = "Proxy not running"
            return
        }
        
        isLoading = true
        defer { isLoading = false }
        
        do {
            guard url.startAccessingSecurityScopedResource() else {
                throw NSError(domain: "Quotio", code: 403, userInfo: [NSLocalizedDescriptionKey: "Permission denied"])
            }
            let data = try Data(contentsOf: url)
            url.stopAccessingSecurityScopedResource()
            
            try await client.uploadVertexServiceAccount(data: data)
            await refreshData()
            errorMessage = nil
        } catch {
            errorMessage = "Import failed: \(error.localizedDescription)"
        }
    }
    
    func clearLogs() async {
        guard let client = apiClient else { return }
        
        do {
            try await client.clearLogs()
            logs.removeAll()
            lastLogTimestamp = nil
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}

struct OAuthState {
    let provider: AIProvider
    var status: OAuthStatus
    var state: String?
    var error: String?
    
    enum OAuthStatus {
        case waiting, polling, success, error
    }
}
