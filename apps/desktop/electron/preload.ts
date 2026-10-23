import { contextBridge, ipcRenderer, webFrame, webUtils } from 'electron'

import type { DesktopProfileRoute } from './desktop-profile'
import type { HudModifierApi, HudModifierStatus } from './hud-modifier-types'
import { customWindowControlsEnabled } from './window-controls'

// Which translucency the OS can back. Asked synchronously because the renderer
// needs it before its first paint, and answered by main because deciding it
// needs `os.release()` — a sandboxed preload may only require electron, events,
// timers and url, so importing node:os here throws before contextBridge runs
// and takes the ENTIRE bridge down with it (window.clawkDesktop undefined =>
// "Desktop IPC bridge is unavailable"). No reply means no glass, which degrades
// to an ordinary opaque window rather than a page thinned over nothing.
const translucencySupport = ipcRenderer.sendSync('clawk:translucency:support')
const hudWindowing = ipcRenderer.sendSync('clawk:hud:windowing')
const hudNativeDrag = hudWindowing?.nativeDrag === true

const launchFlags: { localModels?: boolean; assumeFreshInstall?: boolean } | undefined =
  ipcRenderer.sendSync('clawk:feature-flags')

// Local, sanitized skin payload for the first renderer theme paint. This does
// not wait on `gateway.ready`, so an unreachable remote primary cannot force
// the built-in palette over the skin configured on this machine.
const localSkin = ipcRenderer.sendSync('clawk:skin:local')

import { unwrapExpectedNotFound } from './api-expected-404'

contextBridge.exposeInMainWorld('clawkDesktop', {
  glassSupported: translucencySupport?.glass === true,
  translucencySupported: translucencySupport?.translucency === true,
  // Launch-flag fact: the app was started with --local, so the renderer may
  // show the local-models surfaces. Static for the window's lifetime.
  localModelsEnabled: launchFlags?.localModels === true,
  // Dev-only launch fact: an unpackaged app started with --fresh-install, so
  // onboarding treats this launch as a fresh install. Always false when packaged.
  assumeFreshInstall: launchFlags?.assumeFreshInstall === true,
  localSkin: localSkin && typeof localSkin === 'object' ? localSkin : null,
  getConnection: (profile, opts) => ipcRenderer.invoke('clawk:connection', profile, opts),
  // Loopback origin that hosts YouTube's player for the file:// renderer.
  getEmbedHostOrigin: () => ipcRenderer.invoke('clawk:embed-host:origin'),
  // Registry-scoped backend resolution: { connectionId, profile } → descriptor.
  getConnectionFor: payload => ipcRenderer.invoke('clawk:connection:for', payload),
  getProfileRoutes: profiles => ipcRenderer.invoke('clawk:plugin-profile-routes', profiles),
  revalidateConnection: () => ipcRenderer.invoke('clawk:connection:revalidate'),
  getGatewayWsUrl: profile => ipcRenderer.invoke('clawk:gateway:ws-url', profile),
  // Registry-scoped fresh WS URL: { connectionId, profile } → result shape of
  // getGatewayWsUrl, minted against that connection's backend.
  getGatewayWsUrlFor: payload => ipcRenderer.invoke('clawk:gateway:ws-url-for', payload),
  // { connectionId, profile, pluginId, path } → one-use local plugin socket URL, null, or { refused: 'permission' }.
  getPluginWsUrl: payload => ipcRenderer.invoke('clawk:plugin:ws-url', payload),
  // Union agent roster across every registered connection.
  getAgentRoster: () => ipcRenderer.invoke('clawk:agents:roster'),
  openSessionWindow: (sessionId, opts) => ipcRenderer.invoke('clawk:window:openSession', sessionId, opts),
  openSessionInTerminal: (sessionId, opts) => ipcRenderer.invoke('clawk:window:openInTerminal', sessionId, opts),
  openWindow: (options?: DesktopProfileRoute) => ipcRenderer.invoke('clawk:window:openInstance', options),
  openBrowserWindow: tabId => ipcRenderer.invoke('clawk:window:openBrowser', tabId),
  windowRelay: {
    send: payload => ipcRenderer.send('clawk:window:relay', payload),
    onMessage: callback => {
      const listener = (_event, payload) => callback(payload)
      ipcRenderer.on('clawk:window:relay', listener)

      return () => ipcRenderer.removeListener('clawk:window:relay', listener)
    }
  },
  onBrowserPopoutClosed: callback => {
    const listener = (_event, tabId) => callback(tabId)
    ipcRenderer.on('clawk:browser-popout:closed', listener)

    return () => ipcRenderer.removeListener('clawk:browser-popout:closed', listener)
  },
  claimAmbientCue: key => ipcRenderer.invoke('clawk:ambient:claim', key),
  windowControls: {
    custom: customWindowControlsEnabled(),
    minimize: () => ipcRenderer.send('clawk:window-control', 'minimize'),
    toggleMaximize: () => ipcRenderer.send('clawk:window-control', 'toggle-maximize'),
    close: () => ipcRenderer.send('clawk:window-control', 'close')
  },
  wakeIndicator: {
    getState: () => ipcRenderer.invoke('clawk:wake-indicator:get'),
    setState: state => ipcRenderer.send('clawk:wake-indicator:set', state),
    onState: callback => {
      const listener = (_event, state) => callback(state)
      ipcRenderer.on('clawk:wake-indicator:state', listener)

      return () => ipcRenderer.removeListener('clawk:wake-indicator:state', listener)
    }
  },
  chatOnboarding: {
    size: mode => ipcRenderer.send('clawk:window:size', mode)
  },
  petOverlay: {
    // Main renderer → main process: window lifecycle + drag. `request` is
    // `{ bounds, screen }`; resolves with the screen bounds it actually used.
    open: request => ipcRenderer.invoke('clawk:pet-overlay:open', request),
    close: () => ipcRenderer.invoke('clawk:pet-overlay:close'),
    setBounds: bounds => ipcRenderer.send('clawk:pet-overlay:set-bounds', bounds),
    setIgnoreMouse: ignore => ipcRenderer.send('clawk:pet-overlay:ignore-mouse', ignore),
    // Flip the overlay focusable (and focus it) while the composer needs keys.
    setFocusable: focusable => ipcRenderer.send('clawk:pet-overlay:set-focusable', focusable),
    // Main renderer → overlay (forwarded by main): push the latest pet state.
    pushState: payload => ipcRenderer.send('clawk:pet-overlay:state', payload),
    // Overlay → main renderer (forwarded by main): pop back in / composer submit.
    control: payload => ipcRenderer.send('clawk:pet-overlay:control', payload),
    // Overlay subscribes to state pushes.
    onState: callback => {
      const listener = (_event, payload) => callback(payload)
      ipcRenderer.on('clawk:pet-overlay:state', listener)

      return () => ipcRenderer.removeListener('clawk:pet-overlay:state', listener)
    },
    // Main renderer subscribes to overlay control messages.
    onControl: callback => {
      const listener = (_event, payload) => callback(payload)
      ipcRenderer.on('clawk:pet-overlay:control', listener)

      return () => ipcRenderer.removeListener('clawk:pet-overlay:control', listener)
    }
  },
  // HUD mode: the chrome-free floating chat. A full app renderer (own gateway)
  // sized as a floating bar, so it mounts the real composer. Main owns the
  // window; `onChanged` keeps every window's toggle truthful.
  hud: {
    nativeDrag: hudNativeDrag,
    windowing: {
      clientPlacement: hudWindowing?.clientPlacement !== false,
      controlDrag: hudWindowing?.controlDrag === true,
      nativeDrag: hudNativeDrag,
      solid: hudWindowing?.solid === true,
      workspaceTransfer: hudWindowing?.workspaceTransfer === true
    },
    open: request => ipcRenderer.invoke('clawk:hud:open', request),
    close: () => ipcRenderer.invoke('clawk:hud:close'),
    setIgnoreMouse: ignore => ipcRenderer.send('clawk:hud:ignore-mouse', ignore),
    beginMove: () => ipcRenderer.send('clawk:hud:begin-move'),
    endMove: () => ipcRenderer.send('clawk:hud:end-move'),
    moveBy: delta => ipcRenderer.send('clawk:hud:move-by', delta),
    setWorkspaceTransfer: transferring => ipcRenderer.send('clawk:hud:workspace-transfer', transferring),
    setBounds: bounds => ipcRenderer.send('clawk:hud:set-bounds', bounds),
    resetLayout: () => ipcRenderer.invoke('clawk:hud:reset-layout'),
    // Whether the band covers the window below the bar. Main pairs it with the
    // user's translucency setting to decide the native frost (macOS vibrancy /
    // Windows 11 DWM backdrop) — see hudFrostFor.
    setFrost: showing => ipcRenderer.invoke('clawk:hud:frost', showing),
    // The HUD tells main which session it is on; main hands that back to the
    // app window when the HUD closes, so the app can re-home onto it.
    setSession: sessionId => ipcRenderer.send('clawk:hud:session', sessionId),
    onGoto: callback => {
      const listener = (_event, sessionId) => callback(sessionId)
      ipcRenderer.on('clawk:hud:goto', listener)

      return () => ipcRenderer.removeListener('clawk:hud:goto', listener)
    },
    onChanged: callback => {
      const listener = (_event, state) => callback(state)
      ipcRenderer.on('clawk:hud:changed', listener)

      return () => ipcRenderer.removeListener('clawk:hud:changed', listener)
    },
    // Linux only, and silent elsewhere: where the cursor is, in page
    // coordinates, or null when it has left the window. Stands in for the
    // mousemove that `setIgnoreMouseEvents(true, { forward: true })` delivers on
    // macOS and Windows but not here.
    onCursor: callback => {
      const listener = (_event, point) => callback(point)
      ipcRenderer.on('clawk:hud:cursor', listener)

      return () => ipcRenderer.removeListener('clawk:hud:cursor', listener)
    },
    // Main's game-overlay watch: whether a fullscreen app (a game) is under
    // the HUD, so the renderer can step back to the low-opacity overlay
    // treatment while one owns the screen.
    onGameOverlay: callback => {
      const listener = (_event, state) => callback(state)
      ipcRenderer.on('clawk:hud:game-overlay', listener)

      return () => ipcRenderer.removeListener('clawk:hud:game-overlay', listener)
    }
  },
  hudModifier: {
    getSettings: () => ipcRenderer.invoke('clawk:hud-modifier:settings:get'),
    setEnabled: enabled => ipcRenderer.invoke('clawk:hud-modifier:settings:set', enabled),
    openPermissionSettings: () => ipcRenderer.invoke('clawk:hud-modifier:permission'),
    onStatus: callback => {
      const listener = (_event: Electron.IpcRendererEvent, status: HudModifierStatus) => callback(status)
      ipcRenderer.on('clawk:hud-modifier:status', listener)

      return () => ipcRenderer.removeListener('clawk:hud-modifier:status', listener)
    }
  } satisfies HudModifierApi,
  // macOS native screenshot gesture; captures require a main-issued request.
  screenshot:
    process.platform === 'darwin'
      ? {
          getSettings: () => ipcRenderer.invoke('clawk:screenshot:settings:get'),
          setEnabled: enabled => ipcRenderer.invoke('clawk:screenshot:settings:set', enabled),
          openPermissionSettings: kind => ipcRenderer.invoke('clawk:screenshot:permission', kind),
          capture: requestId => ipcRenderer.invoke('clawk:screenshot:capture', requestId),
          onStatus: callback => {
            const listener = (_event, status) => callback(status)
            ipcRenderer.on('clawk:screenshot:status', listener)

            return () => ipcRenderer.removeListener('clawk:screenshot:status', listener)
          },
          onRequest: callback => {
            const channel = 'clawk:screenshot:request'
            const listener = (_event, requestId) => callback(requestId)

            if (ipcRenderer.listenerCount(channel) === 0) {
              ipcRenderer.send('clawk:screenshot:subscribe', true)
            }

            ipcRenderer.on(channel, listener)

            return () => {
              ipcRenderer.removeListener(channel, listener)

              if (ipcRenderer.listenerCount(channel) === 0) {
                ipcRenderer.send('clawk:screenshot:subscribe', false)
              }
            }
          }
        }
      : undefined,
  // Quick Entry: the global-hotkey mini composer window. Main owns the OS
  // shortcut + the persisted preference; the quick window only captures text
  // and hands it back, and the primary renderer submits it through the normal
  // prompt path.
  quickEntry: {
    getSettings: () => ipcRenderer.invoke('clawk:quick-entry:settings:get'),
    setSettings: patch => ipcRenderer.invoke('clawk:quick-entry:settings:set', patch),
    // Invoke returns the delivery result so the draft is not lost (#85590).
    submit: payload => ipcRenderer.invoke('clawk:quick-entry:submit', payload),
    // Main cannot invoke the primary renderer, so it receives this ack (#85590).
    ackSubmit: (correlationId, result) => ipcRenderer.send('clawk:quick-entry:ack', { correlationId, result }),
    dismiss: () => ipcRenderer.send('clawk:quick-entry:dismiss'),
    // Primary renderer → main → quick window: gateway connection state + the
    // recent-session options the target picker offers. Main caches the latest
    // payload so a freshly spawned quick window starts from truth.
    pushState: payload => ipcRenderer.send('clawk:quick-entry:state', payload),
    // Quick window subscribes to those pushes.
    onState: callback => {
      const listener = (_event, payload) => callback(payload)
      ipcRenderer.on('clawk:quick-entry:state', listener)

      return () => ipcRenderer.removeListener('clawk:quick-entry:state', listener)
    },
    // Main → primary renderer: a submit captured by the quick window.
    onSubmit: callback => {
      const listener = (_event, payload) => callback(payload)
      ipcRenderer.on('clawk:quick-entry:submit', listener)

      return () => ipcRenderer.removeListener('clawk:quick-entry:submit', listener)
    },
    // Main → quick window: you were just summoned (reset draft + refocus).
    onShown: callback => {
      const listener = () => callback()
      ipcRenderer.on('clawk:quick-entry:shown', listener)

      return () => ipcRenderer.removeListener('clawk:quick-entry:shown', listener)
    },
    // Main → quick window: the outcome of a submit whose relay already timed
    // out. Delivery is now KNOWN — reconcile the unknown state instead of
    // leaving the user to resend a prompt that may already be delivered.
    onLateResult: callback => {
      const listener = (_event, payload) => callback(payload)
      ipcRenderer.on('clawk:quick-entry:late-result', listener)

      return () => ipcRenderer.removeListener('clawk:quick-entry:late-result', listener)
    }
  },
  getBootProgress: () => ipcRenderer.invoke('clawk:boot-progress:get'),
  getConnectionConfig: profile => ipcRenderer.invoke('clawk:connection-config:get', profile),
  saveConnectionConfig: payload => ipcRenderer.invoke('clawk:connection-config:save', payload),
  applyConnectionConfig: payload => ipcRenderer.invoke('clawk:connection-config:apply', payload),
  testConnectionConfig: payload => ipcRenderer.invoke('clawk:connection-config:test', payload),
  // Opt-in OS-keychain encryption for stored gateway secrets (default off —
  // see secret-storage-policy.ts). get never touches the OS keychain.
  getSecretStorageEncryption: () => ipcRenderer.invoke('clawk:secret-storage:get'),
  setSecretStorageEncryption: (on: boolean) => ipcRenderer.invoke('clawk:secret-storage:set', on),
  // v2 multi-connection registry: named agent sources (local / remote / cloud / ssh).
  connections: {
    list: () => ipcRenderer.invoke('clawk:connections:list'),
    save: payload => ipcRenderer.invoke('clawk:connections:save', payload),
    remove: id => ipcRenderer.invoke('clawk:connections:remove', id),
    setPrimary: id => ipcRenderer.invoke('clawk:connections:set-primary', id),
    setLaunchMode: mode => ipcRenderer.invoke('clawk:connections:set-launch-mode', mode),
    setLastUsed: id => ipcRenderer.invoke('clawk:connections:set-last-used', id),
    test: id => ipcRenderer.invoke('clawk:connections:test', id),
    updateManaged: id => ipcRenderer.invoke('clawk:connections:update-managed', id),
    // Fan out `clawk update` to every eligible registered connection.
    // Optional excludeIds skips rows the caller updates through another path.
    updateAll: options => ipcRenderer.invoke('clawk:connections:update-all', options),
    // Registry lifecycle push (main → renderer): a connection was removed or
    // materially edited, so secondaries scoped to it must be disposed (and,
    // for edits, re-dialed at the new target).
    onChanged: callback => {
      const listener = (_event, payload) => callback(payload)
      ipcRenderer.on('clawk:connections:changed', listener)

      return () => ipcRenderer.removeListener('clawk:connections:changed', listener)
    }
  },
  sshConfigHosts: () => ipcRenderer.invoke('clawk:ssh-config:hosts'),
  sshResolveHost: host => ipcRenderer.invoke('clawk:ssh-config:resolve', host),
  probeConnectionConfig: remoteUrl => ipcRenderer.invoke('clawk:connection-config:probe', remoteUrl),
  // `options` lets a registry-editor draft sign in BEFORE it is saved: the
  // main process settles the draft's connection id up front so the login
  // window writes into the per-connection cookie jar the saved entry will
  // read (not the legacy shared jar an unsaved URL would fall back to).
  oauthLoginConnectionConfig: (remoteUrl, options) =>
    ipcRenderer.invoke('clawk:connection-config:oauth-login', remoteUrl, options),
  oauthLogoutConnectionConfig: remoteUrl => ipcRenderer.invoke('clawk:connection-config:oauth-logout', remoteUrl),
  // Clawksis Cloud: one portal login powers discovery + silent per-agent sign-in
  // (cloud-auto-discovery Phase 3).
  cloud: {
    status: () => ipcRenderer.invoke('clawk:cloud:status'),
    login: () => ipcRenderer.invoke('clawk:cloud:login'),
    logout: () => ipcRenderer.invoke('clawk:cloud:logout'),
    discover: org => ipcRenderer.invoke('clawk:cloud:discover', org),
    agentSignIn: dashboardUrl => ipcRenderer.invoke('clawk:cloud:agent-sign-in', dashboardUrl)
  },
  profile: {
    getDefault: () => ipcRenderer.invoke('clawk:profile:default:get'),
    setDefault: (route: DesktopProfileRoute) => ipcRenderer.invoke('clawk:profile:default:set', route),
    onDefaultChanged: (callback: (route: DesktopProfileRoute | null) => void) => {
      const listener = (_event: Electron.IpcRendererEvent, route: DesktopProfileRoute | null) => callback(route)
      ipcRenderer.on('clawk:profile:default:changed', listener)

      return () => ipcRenderer.removeListener('clawk:profile:default:changed', listener)
    },
    get: () => ipcRenderer.invoke('clawk:profile:get'),
    remember: name => ipcRenderer.invoke('clawk:profile:remember', name),
    set: name => ipcRenderer.invoke('clawk:profile:set', name)
  },
  // The handler resolves an expected 404 with a sentinel instead of rejecting
  // (Electron logs a stack for every rejected invoke). Turn it back into the
  // rejection the renderer expects — see electron/api-expected-404.ts.
  api: request => ipcRenderer.invoke('clawk:api', request).then(unwrapExpectedNotFound),
  notify: payload => ipcRenderer.invoke('clawk:notify', payload),
  claimStartupLatency: () => ipcRenderer.invoke('clawk:startup-latency:claim'),
  requestMicrophoneAccess: () => ipcRenderer.invoke('clawk:requestMicrophoneAccess'),
  readWindowBelow: () => ipcRenderer.invoke('clawk:window:readBelow'),
  readFileDataUrl: filePath => ipcRenderer.invoke('clawk:readFileDataUrl', filePath),
  readFileDataUrlForAttach: filePath => ipcRenderer.invoke('clawk:readFileDataUrlForAttach', filePath),
  dataUrlReadMax: {
    get: () => ipcRenderer.invoke('clawk:data-url-read-max:get'),
    set: maxMb => ipcRenderer.invoke('clawk:data-url-read-max:set', maxMb)
  },
  readFileText: filePath => ipcRenderer.invoke('clawk:readFileText', filePath),
  readPluginSource: (filePath: string) => ipcRenderer.invoke('clawk:readPluginSource', filePath),
  selectPaths: options => ipcRenderer.invoke('clawk:selectPaths', options),
  selectSavePath: options => ipcRenderer.invoke('clawk:selectSavePath', options),
  saveTextFileAs: request => ipcRenderer.invoke('clawk:saveTextFileAs', request),
  writeClipboard: text => ipcRenderer.invoke('clawk:writeClipboard', text),
  readClipboard: () => ipcRenderer.invoke('clawk:readClipboard'),
  saveGatewayFile: payload => ipcRenderer.invoke('clawk:saveGatewayFile', payload),
  saveImageFromUrl: url => ipcRenderer.invoke('clawk:saveImageFromUrl', url),
  contextMenuEdit: command => ipcRenderer.invoke('clawk:context-menu:edit', command),
  contextMenuCopyImage: () => ipcRenderer.invoke('clawk:context-menu:copy-image'),
  contextMenuSpellcheck: action => ipcRenderer.invoke('clawk:context-menu:spellcheck', action),
  contextMenuGuestAddWord: payload => ipcRenderer.invoke('clawk:context-menu:guest-add-word', payload),
  onContextMenuSpellcheck: callback => {
    const listener = (_event, payload) => callback(payload)
    ipcRenderer.on('clawk:context-menu-spellcheck', listener)

    return () => ipcRenderer.removeListener('clawk:context-menu-spellcheck', listener)
  },
  saveImageBuffer: (data, ext, name) => ipcRenderer.invoke('clawk:saveImageBuffer', { data, ext, name }),
  capturePreview: payload => ipcRenderer.invoke('clawk:capturePreview', payload),
  savePastedText: text => ipcRenderer.invoke('clawk:savePastedText', { text }),
  saveClipboardImage: () => ipcRenderer.invoke('clawk:saveClipboardImage'),
  getPathForFile: file => {
    try {
      return webUtils.getPathForFile(file) || ''
    } catch {
      return ''
    }
  },
  normalizePreviewTarget: (target, baseDir) => ipcRenderer.invoke('clawk:normalizePreviewTarget', target, baseDir),
  watchPreviewFile: url => ipcRenderer.invoke('clawk:watchPreviewFile', url),
  watchDirectory: dir => ipcRenderer.invoke('clawk:watchDirectory', dir),
  stopPreviewFileWatch: id => ipcRenderer.invoke('clawk:stopPreviewFileWatch', id),
  setActiveWork: payload => ipcRenderer.send('clawk:active-work', payload),
  setTitleBarTheme: payload => ipcRenderer.send('clawk:titlebar-theme', payload),
  setNativeTheme: mode => ipcRenderer.send('clawk:native-theme', mode),
  setTranslucency: payload => ipcRenderer.send('clawk:translucency', payload),
  setKeepAwake: mode => ipcRenderer.send('clawk:keep-awake', mode),
  // Once per computer, after a timed sleep interrupted a turn with keep-awake off.
  onKeepAwakeOffer: callback => {
    const listener = () => callback()
    ipcRenderer.on('clawk:keep-awake-offer', listener)

    return () => ipcRenderer.removeListener('clawk:keep-awake-offer', listener)
  },
  minimizeToTray: {
    get: () => ipcRenderer.invoke('clawk:minimize-to-tray:get'),
    set: on => ipcRenderer.invoke('clawk:minimize-to-tray:set', on),
    onChanged: callback => {
      const listener = (_event, status) => callback(status)
      ipcRenderer.on('clawk:minimize-to-tray:changed', listener)

      return () => ipcRenderer.removeListener('clawk:minimize-to-tray:changed', listener)
    }
  },
  setDisableF12: blocked => ipcRenderer.send('clawk:devtools:disable-f12', blocked),
  setF12ShortcutActive: active => ipcRenderer.send('clawk:f12ShortcutActive', Boolean(active)),
  onF12Shortcut: callback => {
    const listener = (_event, input) => callback(input)
    ipcRenderer.on('clawk:f12-shortcut', listener)

    return () => ipcRenderer.removeListener('clawk:f12-shortcut', listener)
  },
  setPreviewShortcutActive: active => ipcRenderer.send('clawk:previewShortcutActive', Boolean(active)),
  setPreviewGuestHidden: (webContentsId, hidden) =>
    ipcRenderer.send('clawk:preview-guest-hidden', { webContentsId, hidden: Boolean(hidden) }),
  openExternal: url => ipcRenderer.invoke('clawk:openExternal', url),
  freeTierChallenge: {
    // Load the account service's challenge page in a hidden window (revealed
    // only if the page asks for the human). Resolves with how it ended.
    run: request => ipcRenderer.invoke('clawk:freeTierChallenge:run', request)
  },
  mcpOauth: {
    // One-shot loopback listener for MCP OAuth against remote backends: bind
    // on this machine, hand redirectUri to mcp.servers.oauth.start, then wait
    // for the provider redirect and relay code/state via oauth.callback.
    listen: () => ipcRenderer.invoke('clawk:mcp-oauth:listen'),
    wait: (id, timeoutMs) => ipcRenderer.invoke('clawk:mcp-oauth:wait', id, timeoutMs),
    cancel: id => ipcRenderer.invoke('clawk:mcp-oauth:cancel', id)
  },
  openPreviewInBrowser: url => ipcRenderer.invoke('clawk:openPreviewInBrowser', url),
  reachPreviewUrl: url => ipcRenderer.invoke('clawk:preview:reach', url),
  setActiveConnectionRoute: route => ipcRenderer.send('clawk:connection:active-route', route),
  fetchLinkTitle: url => ipcRenderer.invoke('clawk:fetchLinkTitle', url),
  resolveFavicon: url => ipcRenderer.invoke('clawk:resolveFavicon', url),
  sanitizeWorkspaceCwd: cwd => ipcRenderer.invoke('clawk:workspace:sanitize', cwd),
  settings: {
    getDefaultProjectDir: () => ipcRenderer.invoke('clawk:setting:defaultProjectDir:get'),
    setDefaultProjectDir: dir => ipcRenderer.invoke('clawk:setting:defaultProjectDir:set', dir),
    pickDefaultProjectDir: () => ipcRenderer.invoke('clawk:setting:defaultProjectDir:pick')
  },
  preparedSubmissions: {
    read: () => ipcRenderer.invoke('clawk:prepared-submissions:read'),
    update: (key, entry) => ipcRenderer.invoke('clawk:prepared-submissions:update', key, entry),
    compareAndSet: (key, expected, entry) =>
      ipcRenderer.invoke('clawk:prepared-submissions:compare-and-set', key, expected, entry)
  },
  zoom: {
    // Current zoom of this window, as { level, percent }.
    get: () => ipcRenderer.invoke('clawk:zoom:get'),
    // Synchronous zoom factor (1 = 100%). Coordinate math needs it in the
    // same tick as the event it converts, so no IPC round-trip here.
    factor: () => webFrame.getZoomFactor(),
    setPercent: percent => ipcRenderer.send('clawk:zoom:set-percent', percent),
    // Fires on every zoom change, including the Ctrl/Cmd +/-/0 shortcuts,
    // so the settings UI can stay in sync with the keyboard.
    onChanged: callback => {
      const listener = (_event, payload) => callback(payload)
      ipcRenderer.on('clawk:zoom:changed', listener)

      return () => ipcRenderer.removeListener('clawk:zoom:changed', listener)
    }
  },
  revealLogs: () => ipcRenderer.invoke('clawk:logs:reveal'),
  getRecentLogs: () => ipcRenderer.invoke('clawk:logs:recent'),
  // Fire-and-forget: persists a renderer error-boundary catch (with component
  // stack) to desktop.log so crashes survive the window (#79428).
  reportRendererError: report => ipcRenderer.send('clawk:logs:renderer-error', report),
  logLine: (line: string): void => ipcRenderer.send('clawk:logs:renderer-line', line),
  readDir: dirPath => ipcRenderer.invoke('clawk:fs:readDir', dirPath),
  gitRoot: startPath => ipcRenderer.invoke('clawk:fs:gitRoot', startPath),
  revealPath: targetPath => ipcRenderer.invoke('clawk:fs:reveal', targetPath),
  openDir: dirPath => ipcRenderer.invoke('clawk:fs:openDir', dirPath),
  desktopPluginsRoot: () => ipcRenderer.invoke('clawk:fs:desktopPluginsRoot'),
  reconcileDesktopPlugins: () => ipcRenderer.invoke('clawk:fs:reconcileDesktopPlugins'),
  logsRoot: (profile?: string) => ipcRenderer.invoke('clawk:fs:logsRoot', profile),
  renamePath: (targetPath, newName) => ipcRenderer.invoke('clawk:fs:rename', targetPath, newName),
  writeTextFile: (filePath, content) => ipcRenderer.invoke('clawk:fs:writeText', filePath, content),
  trashPath: targetPath => ipcRenderer.invoke('clawk:fs:trash', targetPath),
  git: {
    worktreeList: repoPath => ipcRenderer.invoke('clawk:git:worktreeList', repoPath),
    worktreeAdd: (repoPath, options) => ipcRenderer.invoke('clawk:git:worktreeAdd', repoPath, options),
    worktreeRemove: (repoPath, worktreePath, options) =>
      ipcRenderer.invoke('clawk:git:worktreeRemove', repoPath, worktreePath, options),
    branchSwitch: (repoPath, branch) => ipcRenderer.invoke('clawk:git:branchSwitch', repoPath, branch),
    branchList: repoPath => ipcRenderer.invoke('clawk:git:branchList', repoPath),
    baseBranchList: repoPath => ipcRenderer.invoke('clawk:git:baseBranchList', repoPath),
    repoStatus: repoPath => ipcRenderer.invoke('clawk:git:repoStatus', repoPath),
    fileDiff: (repoPath, filePath) => ipcRenderer.invoke('clawk:git:fileDiff', repoPath, filePath),
    scanRepos: (roots, options) => ipcRenderer.invoke('clawk:git:scanRepos', roots, options),
    review: {
      list: (repoPath, scope, baseRef) => ipcRenderer.invoke('clawk:git:review:list', repoPath, scope, baseRef),
      diff: (repoPath, filePath, scope, baseRef, staged) =>
        ipcRenderer.invoke('clawk:git:review:diff', repoPath, filePath, scope, baseRef, staged),
      stage: (repoPath, filePath) => ipcRenderer.invoke('clawk:git:review:stage', repoPath, filePath),
      unstage: (repoPath, filePath) => ipcRenderer.invoke('clawk:git:review:unstage', repoPath, filePath),
      revert: (repoPath, filePath) => ipcRenderer.invoke('clawk:git:review:revert', repoPath, filePath),
      revParse: (repoPath, ref) => ipcRenderer.invoke('clawk:git:review:revParse', repoPath, ref),
      commit: (repoPath, message, push) => ipcRenderer.invoke('clawk:git:review:commit', repoPath, message, push),
      commitContext: repoPath => ipcRenderer.invoke('clawk:git:review:commitContext', repoPath),
      push: repoPath => ipcRenderer.invoke('clawk:git:review:push', repoPath),
      shipInfo: repoPath => ipcRenderer.invoke('clawk:git:review:shipInfo', repoPath),
      prList: (repoPath, branches, numbers) =>
        ipcRenderer.invoke('clawk:git:review:prList', repoPath, branches, numbers),
      createPr: repoPath => ipcRenderer.invoke('clawk:git:review:createPr', repoPath)
    }
  },
  terminal: {
    attach: id => ipcRenderer.invoke('clawk:terminal:attach', id),
    cwd: id => ipcRenderer.invoke('clawk:terminal:cwd', id),
    dispose: id => ipcRenderer.invoke('clawk:terminal:dispose', id),
    resize: (id, size) => ipcRenderer.invoke('clawk:terminal:resize', id, size),
    start: options => ipcRenderer.invoke('clawk:terminal:start', options),
    write: (id, data) => ipcRenderer.invoke('clawk:terminal:write', id, data),
    onData: (id, callback) => {
      const channel = `clawk:terminal:${id}:data`
      const listener = (_event, payload) => callback(payload)
      ipcRenderer.on(channel, listener)

      return () => ipcRenderer.removeListener(channel, listener)
    },
    onExit: (id, callback) => {
      const channel = `clawk:terminal:${id}:exit`
      const listener = (_event, payload) => callback(payload)
      ipcRenderer.on(channel, listener)

      return () => ipcRenderer.removeListener(channel, listener)
    }
  },
  onClosePreviewRequested: callback => {
    const listener = () => callback()
    ipcRenderer.on('clawk:close-preview-requested', listener)

    return () => ipcRenderer.removeListener('clawk:close-preview-requested', listener)
  },
  onPreviewNav: callback => {
    const listener = (_event, command) => callback(command)
    ipcRenderer.on('clawk:preview-nav', listener)

    return () => ipcRenderer.removeListener('clawk:preview-nav', listener)
  },
  onOpenFolderRequested: callback => {
    const listener = () => callback()
    ipcRenderer.on('clawk:open-folder-requested', listener)

    return () => ipcRenderer.removeListener('clawk:open-folder-requested', listener)
  },
  onOpenUpdatesRequested: callback => {
    const listener = () => callback()
    ipcRenderer.on('clawk:open-updates', listener)

    return () => ipcRenderer.removeListener('clawk:open-updates', listener)
  },
  onDeepLink: callback => {
    const listener = (_event, payload) => callback(payload)
    ipcRenderer.on('clawk:deep-link', listener)

    return () => ipcRenderer.removeListener('clawk:deep-link', listener)
  },
  signalDeepLinkReady: () => ipcRenderer.invoke('clawk:deep-link-ready'),
  probePluginRepo: payload => ipcRenderer.invoke('clawk:plugin:probe', payload),
  installDesktopPlugin: payload => ipcRenderer.invoke('clawk:plugin:installDesktop', payload),
  removeDesktopPlugin: payload => ipcRenderer.invoke('clawk:plugin:removeDesktop', payload),
  onWindowStateChanged: callback => {
    const listener = (_event, payload) => callback(payload)
    ipcRenderer.on('clawk:window-state-changed', listener)

    return () => ipcRenderer.removeListener('clawk:window-state-changed', listener)
  },
  onFocusSession: callback => {
    const listener = (_event, sessionId) => callback(sessionId)
    ipcRenderer.on('clawk:focus-session', listener)

    return () => ipcRenderer.removeListener('clawk:focus-session', listener)
  },
  onNotificationAction: callback => {
    const listener = (_event, payload) => callback(payload)
    ipcRenderer.on('clawk:notification-action', listener)

    return () => ipcRenderer.removeListener('clawk:notification-action', listener)
  },
  onNotificationActivate: callback => {
    const listener = (_event, payload) => callback(payload)
    ipcRenderer.on('clawk:notification-activate', listener)

    return () => ipcRenderer.removeListener('clawk:notification-activate', listener)
  },
  onExternalOpenFailed: callback => {
    const listener = (_event, payload) => callback(payload)
    ipcRenderer.on('clawk:external-open-failed', listener)

    return () => ipcRenderer.removeListener('clawk:external-open-failed', listener)
  },
  onPreviewFileChanged: callback => {
    const listener = (_event, payload) => callback(payload)
    ipcRenderer.on('clawk:preview-file-changed', listener)

    return () => ipcRenderer.removeListener('clawk:preview-file-changed', listener)
  },
  onBackendExit: callback => {
    const listener = (_event, payload) => callback(payload)
    ipcRenderer.on('clawk:backend-exit', listener)

    return () => ipcRenderer.removeListener('clawk:backend-exit', listener)
  },
  // Soft gateway-mode apply finished tearing down the primary backend. Renderer
  // should wipe session lists + re-dial without a window reload.
  onConnectionApplied: callback => {
    const listener = () => callback()
    ipcRenderer.on('clawk:connection:applied', listener)

    return () => ipcRenderer.removeListener('clawk:connection:applied', listener)
  },
  onPowerResume: callback => {
    const listener = () => callback()
    ipcRenderer.on('clawk:power-resume', listener)

    return () => ipcRenderer.removeListener('clawk:power-resume', listener)
  },
  // AC ↔ battery transitions; renderers slow their backstop polls on battery.
  getOnBattery: () => ipcRenderer.invoke('clawk:power-battery:get'),
  onBatteryChanged: callback => {
    const listener = (_event, onBattery) => callback(Boolean(onBattery))
    ipcRenderer.on('clawk:power-battery', listener)

    return () => ipcRenderer.removeListener('clawk:power-battery', listener)
  },
  onBootProgress: callback => {
    const listener = (_event, payload) => callback(payload)
    ipcRenderer.on('clawk:boot-progress', listener)

    return () => ipcRenderer.removeListener('clawk:boot-progress', listener)
  },
  // First-launch bootstrap progress -- emitted by the install.ps1 stage
  // runner in main.ts (apps/desktop/electron/bootstrap-runner.ts).
  // Renderer's install overlay subscribes to live events and queries the
  // current snapshot via getBootstrapState() to recover after a devtools
  // reload mid-bootstrap.
  getBootstrapState: () => ipcRenderer.invoke('clawk:bootstrap:get'),
  probeLocalBackend: () => ipcRenderer.invoke('clawk:local-backend:probe'),
  continueBootstrapLocal: () => ipcRenderer.invoke('clawk:bootstrap:continue-local'),
  recycleBackend: profile => ipcRenderer.invoke('clawk:backend:recycle', profile),
  resetBootstrap: () => ipcRenderer.invoke('clawk:bootstrap:reset'),
  updateHold: {
    recheck: () => ipcRenderer.invoke('clawk:update-hold:recheck'),
    quit: () => ipcRenderer.invoke('clawk:update-hold:quit'),
    startAnyway: (request: { holdId: string; confirmed: true }) =>
      ipcRenderer.invoke('clawk:update-hold:start-anyway', request)
  },
  repairBootstrap: () => ipcRenderer.invoke('clawk:bootstrap:repair'),
  cancelBootstrap: () => ipcRenderer.invoke('clawk:bootstrap:cancel'),
  onBootstrapEvent: callback => {
    const listener = (_event, payload) => callback(payload)
    ipcRenderer.on('clawk:bootstrap:event', listener)

    return () => ipcRenderer.removeListener('clawk:bootstrap:event', listener)
  },
  getVersion: () => ipcRenderer.invoke('clawk:version'),
  relaunchApp: () => ipcRenderer.invoke('clawk:app:relaunch'),
  getMachineProfile: () => ipcRenderer.invoke('clawk:machine:profile'),
  getRemoteDisplayReason: () => ipcRenderer.invoke('clawk:get-remote-display-reason'),
  uninstall: {
    summary: () => ipcRenderer.invoke('clawk:uninstall:summary'),
    run: mode => ipcRenderer.invoke('clawk:uninstall:run', { mode }),
    openAppsSettings: () => ipcRenderer.invoke('clawk:uninstall:openAppsSettings')
  },
  updates: {
    check: opts => ipcRenderer.invoke('clawk:updates:check', opts),
    apply: opts => ipcRenderer.invoke('clawk:updates:apply', opts),
    setChannel: name => ipcRenderer.invoke('clawk:updates:channel:set', name),
    onProgress: callback => {
      const listener = (_event, payload) => callback(payload)
      ipcRenderer.on('clawk:updates:progress', listener)

      return () => ipcRenderer.removeListener('clawk:updates:progress', listener)
    },
    takePendingRun: () => ipcRenderer.invoke('clawk:updates:metric:take'),
    ackPendingRun: sent => ipcRenderer.invoke('clawk:updates:metric:ack', sent),
    onPendingRun: callback => {
      const listener = () => callback()
      ipcRenderer.on('clawk:updates:metric:pending', listener)

      return () => ipcRenderer.removeListener('clawk:updates:metric:pending', listener)
    }
  },
  desktopMetrics: {
    setEnabled: (on, profile) => ipcRenderer.invoke('clawk:desktop-metrics:set-enabled', on, profile),
    takeRendererCrashes: () => ipcRenderer.invoke('clawk:desktop-metrics:crash:take'),
    ackRendererCrashes: sent => ipcRenderer.invoke('clawk:desktop-metrics:crash:ack', sent)
  },
  themes: {
    fetchMarketplace: id => ipcRenderer.invoke('clawk:vscode-theme:fetch', id),
    searchMarketplace: query => ipcRenderer.invoke('clawk:vscode-theme:search', query)
  },
  // Find-in-page (Ctrl/Cmd+F): delegates to Electron's
  // webContents.findInPage on the IPC sender's window so a Cmd+F pressed
  // in a secondary session window searches THAT window, not the primary.
  // `onFoundInPage` returns the unsubscribe fn; the renderer wires it via
  // `initFindInPageListener` in store/find-in-page.ts and tears it down
  // when the FindBar unmounts.
  findInPage: (query, options) => ipcRenderer.invoke('clawk:find-in-page', query, options),
  stopFindInPage: () => ipcRenderer.invoke('clawk:stop-find-in-page'),
  onFoundInPage: callback => {
    const listener = (_event, result) => callback(result)
    ipcRenderer.on('clawk:found-in-page', listener)

    return () => ipcRenderer.removeListener('clawk:found-in-page', listener)
  },
  // Main-process `before-input-event` forwards Ctrl/Cmd+F here so renderer
  // can open the FindBar even when the GTK compositor has already grabbed
  // the chord at the windowing layer (#81727).
  onOpenFindBarRequested: callback => {
    const listener = () => callback()
    ipcRenderer.on('clawk:open-find-bar', listener)

    return () => ipcRenderer.removeListener('clawk:open-find-bar', listener)
  }
})
