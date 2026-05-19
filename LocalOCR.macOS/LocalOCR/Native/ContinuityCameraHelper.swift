import AppKit
import AVFoundation

/// Continuity Camera availability check + photo import (§2.3 win, §4.6 Integration 10).
///
/// Phase 5: minimal API — returns true if a Continuity Camera device is currently
/// nearby. Full capture flow uses the standard macOS "Import from iPhone or iPad"
/// menu command which is auto-wired by AppKit's Edit menu on macOS 13+.
@MainActor
enum ContinuityCameraHelper {

    static var isAvailable: Bool {
        // .external + .continuityCamera are macOS 14+. On 13.x fall back to
        // the legacy externalUnknown device type and check for any external
        // video capture device.
        let deviceTypes: [AVCaptureDevice.DeviceType]
        if #available(macOS 14.0, *) {
            deviceTypes = [.external, .continuityCamera]
        } else {
            deviceTypes = [.externalUnknown]
        }
        let session = AVCaptureDevice.DiscoverySession(
            deviceTypes: deviceTypes,
            mediaType: .video,
            position: .unspecified
        )
        return !session.devices.isEmpty
    }
}
