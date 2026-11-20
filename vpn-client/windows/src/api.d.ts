export interface Profile { id: string; name: string; host: string; port: number; sni: string; fingerprint: string }
export interface Prefs { mode: 'proxy'|'vpn'; ruDirect: boolean; interface: string; socksPort: number; httpPort: number; apiPort: number; manageProxy: boolean; strictDns: boolean; directDomains: string; proxyDomains: string; theme: string }
export interface State { profiles: Profile[]; selected: string; prefs: Prefs; startup: { available: boolean; enabled: boolean; portable: boolean; disabledByWindows: boolean }; connection: { phase: string; stage: string; mode?: string; error: string; up: number; down: number; upRate: number; downRate: number; since: number; health: 'unknown'|'checking'|'online'|'degraded'; healthMessage: string; latency: number|null; checkedAt: number; lastOnline: number; statsStatus: 'pending'|'ready'|'stale'; statsAt: number; timings: Record<string, number> }; version: string }
declare global {
  interface Window {
    reality: {
      initial(): Promise<State>; importProfile(uri: string): Promise<State>; removeProfile(id: string): Promise<State>; selectProfile(id: string): Promise<State>;
      connect(mode: string): Promise<State>; disconnect(): Promise<State>; recheck(): Promise<State>; savePrefs(prefs: Prefs): Promise<State>; interfaces(): Promise<string[]>;
      startup(): Promise<State>; setStartup(enabled: boolean): Promise<State>;
      clipboard(): Promise<string>; copyAccess(id: string): Promise<void>; diagnostics(): Promise<string>; minimize(): Promise<void>; close(): Promise<void>;
      onState(listener: (state: State) => void): () => void;
    }
  }
}
