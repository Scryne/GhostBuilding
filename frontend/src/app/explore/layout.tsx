// ═══════════════════════════════════════════════════════════════════════════
// Explore Layout — Body overflow override
// Ana sayfa harita tam ekran (overflow:hidden), explore sayfası scroll ister.
// ═══════════════════════════════════════════════════════════════════════════

export default function ExploreLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="min-h-screen overflow-y-auto" style={{ overflow: "auto" }}>
      <style>{`body { overflow: auto !important; }`}</style>
      {children}
    </div>
  );
}
