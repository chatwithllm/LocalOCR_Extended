#!/usr/bin/env swift

// Generates the LocalOCR app icon set.
// Usage: swift scripts/generate-app-icon.swift
//
// Produces PNGs in LocalOCR/Resources/Assets.xcassets/AppIcon.appiconset/
// matching the size manifest already defined in Contents.json.

import AppKit
import CoreGraphics
import Foundation

let outDir = "LocalOCR/Resources/Assets.xcassets/AppIcon.appiconset"
let fm = FileManager.default
guard fm.fileExists(atPath: outDir) else {
    FileHandle.standardError.write("Run from LocalOCR.macOS/ — \(outDir) not found.\n".data(using: .utf8)!)
    exit(1)
}

struct Size { let pt: Int; let scale: Int; var px: Int { pt * scale } }

let sizes: [Size] = [
    .init(pt: 16,  scale: 1), .init(pt: 16,  scale: 2),
    .init(pt: 32,  scale: 1), .init(pt: 32,  scale: 2),
    .init(pt: 128, scale: 1), .init(pt: 128, scale: 2),
    .init(pt: 256, scale: 1), .init(pt: 256, scale: 2),
    .init(pt: 512, scale: 1), .init(pt: 512, scale: 2)
]

let accent = NSColor(srgbRed: 0x3b / 255.0, green: 0x82 / 255.0, blue: 0xf6 / 255.0, alpha: 1.0)
let glyphWhite = NSColor.white

func renderIcon(px: Int) -> NSImage {
    let size = NSSize(width: px, height: px)
    let image = NSImage(size: size)
    image.lockFocus()
    defer { image.unlockFocus() }

    // Rounded-rect background (macOS Big Sur+ style: ~22.4% corner radius).
    let radius = CGFloat(px) * 0.224
    let rect = NSRect(origin: .zero, size: size)
    let path = NSBezierPath(roundedRect: rect, xRadius: radius, yRadius: radius)
    accent.setFill()
    path.fill()

    // Inner SF Symbol-style glyph (doc.text.viewfinder, drawn as crosshair + page).
    let inset = CGFloat(px) * 0.22
    let glyph = NSRect(x: inset, y: inset, width: CGFloat(px) - inset * 2, height: CGFloat(px) - inset * 2)

    // Frame brackets (viewfinder)
    let lineWidth = CGFloat(px) * 0.04
    let bracketLen = glyph.width * 0.20
    glyphWhite.setStroke()

    let bracketPath = NSBezierPath()
    bracketPath.lineWidth = lineWidth
    bracketPath.lineCapStyle = .round
    bracketPath.lineJoinStyle = .round

    // Top-left
    bracketPath.move(to: NSPoint(x: glyph.minX, y: glyph.maxY - bracketLen))
    bracketPath.line(to: NSPoint(x: glyph.minX, y: glyph.maxY))
    bracketPath.line(to: NSPoint(x: glyph.minX + bracketLen, y: glyph.maxY))
    // Top-right
    bracketPath.move(to: NSPoint(x: glyph.maxX - bracketLen, y: glyph.maxY))
    bracketPath.line(to: NSPoint(x: glyph.maxX, y: glyph.maxY))
    bracketPath.line(to: NSPoint(x: glyph.maxX, y: glyph.maxY - bracketLen))
    // Bottom-left
    bracketPath.move(to: NSPoint(x: glyph.minX, y: glyph.minY + bracketLen))
    bracketPath.line(to: NSPoint(x: glyph.minX, y: glyph.minY))
    bracketPath.line(to: NSPoint(x: glyph.minX + bracketLen, y: glyph.minY))
    // Bottom-right
    bracketPath.move(to: NSPoint(x: glyph.maxX - bracketLen, y: glyph.minY))
    bracketPath.line(to: NSPoint(x: glyph.maxX, y: glyph.minY))
    bracketPath.line(to: NSPoint(x: glyph.maxX, y: glyph.minY + bracketLen))
    bracketPath.stroke()

    // Inner page lines (mimic "doc.text")
    let lineSpacing = glyph.height * 0.12
    let lineStartY = glyph.midY + glyph.height * 0.18
    for i in 0..<3 {
        let y = lineStartY - CGFloat(i) * lineSpacing
        let pageLineWidth = (i == 2) ? glyph.width * 0.32 : glyph.width * 0.46
        let p = NSBezierPath()
        p.lineWidth = lineWidth * 0.95
        p.lineCapStyle = .round
        let xStart = glyph.midX - pageLineWidth / 2
        p.move(to: NSPoint(x: xStart, y: y))
        p.line(to: NSPoint(x: xStart + pageLineWidth, y: y))
        p.stroke()
    }

    return image
}

func savePNG(_ image: NSImage, to path: String) {
    guard let tiff = image.tiffRepresentation,
          let rep = NSBitmapImageRep(data: tiff),
          let data = rep.representation(using: .png, properties: [:]) else {
        FileHandle.standardError.write("Failed to encode \(path)\n".data(using: .utf8)!)
        return
    }
    try? data.write(to: URL(fileURLWithPath: path))
}

for s in sizes {
    let image = renderIcon(px: s.px)
    let name = "icon_\(s.pt)x\(s.pt)@\(s.scale)x.png"
    let path = "\(outDir)/\(name)"
    savePNG(image, to: path)
    print("wrote \(name) (\(s.px)×\(s.px))")
}

// Rewrite Contents.json so the manifest references the generated filenames.
let manifest: [String: Any] = [
    "images": sizes.map { s -> [String: String] in
        [
            "idiom": "mac",
            "scale": "\(s.scale)x",
            "size":  "\(s.pt)x\(s.pt)",
            "filename": "icon_\(s.pt)x\(s.pt)@\(s.scale)x.png"
        ]
    },
    "info": ["author": "xcode", "version": 1]
]
if let json = try? JSONSerialization.data(withJSONObject: manifest, options: [.prettyPrinted, .sortedKeys]) {
    try? json.write(to: URL(fileURLWithPath: "\(outDir)/Contents.json"))
    print("wrote Contents.json")
}
print("done.")
