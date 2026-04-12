import Map from '@/components/Map';
import { Layers, Activity, Search, ShieldAlert } from 'lucide-react';

export const metadata = {
  title: 'GhostBuilding | OSINT Mapping Intelligence',
  description: 'Identify discrepancies between mapping providers worldwide dynamically with GhostBuilding.',
};

export default function Home() {
  return (
    <main className="flex min-h-screen flex-col bg-[#050505] text-white font-sans selection:bg-indigo-500/30">
      {/* Navbar */}
      <header className="flex items-center justify-between px-8 py-4 border-b border-white/5 bg-black/40 backdrop-blur-xl sticky top-0 z-50">
        <div className="flex items-center gap-3">
          <div className="p-2 bg-indigo-500/10 rounded-lg border border-indigo-500/20">
            <ShieldAlert className="w-6 h-6 text-indigo-400" />
          </div>
          <h1 className="text-2xl font-bold bg-gradient-to-r from-indigo-400 via-cyan-400 to-teal-400 bg-clip-text text-transparent tracking-tight">
            GhostBuilding
          </h1>
        </div>
        <nav className="hidden md:flex items-center gap-8 text-sm font-medium text-gray-400">
          <a href="#" className="text-white relative after:content-[''] after:absolute after:-bottom-5 after:left-0 after:w-full after:h-[2px] after:bg-indigo-500 hover:text-white transition-colors">Dashboard</a>
          <a href="#" className="hover:text-white transition-colors">OSINT Toolkit</a>
          <a href="#" className="hover:text-white transition-colors">Detections</a>
          <div className="px-5 py-2.5 bg-indigo-600/10 text-indigo-400 border border-indigo-500/20 rounded-full hover:bg-indigo-500/20 hover:shadow-[0_0_15px_rgba(99,102,241,0.2)] transition-all cursor-pointer font-semibold tracking-wide">
            Access Intel
          </div>
        </nav>
      </header>

      <div className="flex flex-1 overflow-hidden p-6 gap-6 h-[calc(100vh-80px)]">
        {/* Sidebar */}
        <aside className="w-[340px] flex flex-col gap-6 h-full">
          {/* Map Layers */}
          <div className="bg-black/40 border border-white/5 rounded-2xl p-5 backdrop-blur-md shadow-xl flex-shrink-0">
            <h2 className="text-sm font-bold tracking-wider uppercase mb-5 text-gray-500 flex items-center gap-2">
              <Layers className="w-4 h-4" /> Data Sources
            </h2>
            <div className="space-y-3">
              {[
                { name: 'Google Maps', color: 'bg-blue-500' },
                { name: 'OpenStreetMap', color: 'bg-green-500' },
                { name: 'Bing Maps', color: 'bg-teal-500' },
                { name: 'Yandex Maps', color: 'bg-red-500' }
              ].map((provider) => (
                <label key={provider.name} className="flex items-center justify-between p-3.5 rounded-xl bg-white/5 hover:bg-white/10 cursor-pointer transition-all border border-transparent hover:border-white/10 group">
                  <div className="flex items-center gap-3">
                    <input type="checkbox" className="peer sr-only" defaultChecked />
                    <div className="w-5 h-5 rounded border border-gray-600 bg-black/50 peer-checked:bg-indigo-500 peer-checked:border-indigo-500 flex items-center justify-center transition-colors">
                      <svg className="w-3 h-3 text-white opacity-0 peer-checked:opacity-100" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M5 13l4 4L19 7" />
                      </svg>
                    </div>
                    <span className="text-sm font-medium text-gray-300 group-hover:text-white transition-colors">{provider.name}</span>
                  </div>
                  <div className={`w-2 h-2 rounded-full ${provider.color} shadow-[0_0_8px_currentColor]`} />
                </label>
              ))}
            </div>
          </div>

          {/* Real-time Activity */}
          <div className="bg-black/40 border border-white/5 rounded-2xl p-5 backdrop-blur-md shadow-xl flex-1 overflow-hidden flex flex-col">
            <h2 className="text-sm font-bold tracking-wider uppercase mb-5 text-gray-500 flex items-center gap-2">
              <Activity className="w-4 h-4" /> Intel Feed
            </h2>
            <div className="space-y-3 overflow-y-auto pr-2 custom-scrollbar flex-1 relative">
              <div className="absolute left-[15px] top-4 bottom-4 w-px bg-white/10" />
              {[
                { id: 1, loc: "Restricted Area B", diff: "Missing in Google Maps", time: "2m ago", status: "critical" },
                { id: 2, loc: "Sector 7G Geometry", diff: "Resolution disparity detected", time: "45m ago", status: "warning" },
                { id: 3, loc: "Unknown Facility", diff: "Present only in local registry", time: "3h ago", status: "info" },
                { id: 4, loc: "Censorship Overlay", diff: "Pixelation filter bypass", time: "5h ago", status: "critical" },
              ].map((item) => (
                <div key={item.id} className="relative pl-10 group cursor-pointer">
                  <div className={`absolute left-[11px] top-1.5 w-2 h-2 rounded-full ring-4 ring-black/50 
                    ${item.status === 'critical' ? 'bg-red-500 shadow-[0_0_10px_rgba(239,68,68,0.8)]' : 
                      item.status === 'warning' ? 'bg-amber-400 shadow-[0_0_10px_rgba(251,191,36,0.8)]' : 
                      'bg-cyan-400 shadow-[0_0_10px_rgba(34,211,238,0.8)]'}`} />
                  <div className="p-4 rounded-xl border border-white/5 bg-white/5 hover:bg-white/10 transition-all hover:border-white/10">
                    <div className="flex justify-between items-start mb-1">
                      <h3 className="text-sm font-semibold text-gray-200 group-hover:text-indigo-300 transition-colors">{item.loc}</h3>
                      <span className="text-[10px] uppercase text-gray-500 font-bold bg-black/40 px-2 py-0.5 rounded-full">{item.time}</span>
                    </div>
                    <p className="text-xs text-gray-400 leading-relaxed">{item.diff}</p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </aside>

        {/* Main Interface */}
        <section className="flex-1 flex flex-col gap-5 min-w-0">
          {/* Top Bar */}
          <div className="flex items-center justify-between bg-black/40 border border-white/5 rounded-2xl px-5 py-3.5 backdrop-blur-md shadow-xl">
            <div className="flex items-center gap-3 w-[45%] bg-black/50 rounded-xl px-4 py-2 border border-white/5 focus-within:border-indigo-500/50 focus-within:ring-1 focus-within:ring-indigo-500/50 transition-all">
              <Search className="w-5 h-5 text-gray-400" />
              <input 
                type="text" 
                placeholder="Analyze intelligence coordinates, areas, or anomalies..." 
                className="bg-transparent border-none outline-none text-sm text-gray-200 w-full placeholder:text-gray-600"
              />
            </div>
            <div className="flex items-center gap-4">
              <div className="flex items-center gap-2 text-xs font-semibold text-teal-400 bg-teal-400/10 px-4 py-2 rounded-xl border border-teal-400/20 shadow-[0_0_15px_rgba(45,212,191,0.1)]">
                <div className="w-1.5 h-1.5 rounded-full bg-teal-400 animate-pulse" />
                Live Synchronization
              </div>
            </div>
          </div>
          
          {/* Map Workspace */}
          <div className="flex-1 rounded-2xl overflow-hidden relative shadow-2xl bg-black">
            <Map />
            {/* Elegant vignette */}
            <div className="absolute inset-0 pointer-events-none shadow-[inset_0_0_100px_rgba(0,0,0,0.8)] z-10" />
          </div>
        </section>
      </div>
    </main>
  );
}
