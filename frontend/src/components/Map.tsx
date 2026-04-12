'use client';


import Map, { NavigationControl, Marker } from 'react-map-gl/maplibre';
import 'maplibre-gl/dist/maplibre-gl.css';
import maplibregl from 'maplibre-gl';

export default function AppMap() {
  return (
    <div className="w-full h-full relative bg-gray-900 border border-white/10 rounded-xl overflow-hidden shadow-[0_0_40px_rgba(99,102,241,0.15)] ring-1 ring-white/10">
      <Map
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        mapLib={maplibregl as any}
        initialViewState={{
          longitude: 35.0,
          latitude: 39.0,
          zoom: 3
        }}
        mapStyle="https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json"
      >
        <NavigationControl position="top-right" />
        
        {/* Sample Highlighted Inconsistency */}
        <Marker longitude={35.3213} latitude={39.0}>
          <div className="relative flex items-center justify-center">
            <div className="absolute w-8 h-8 bg-red-500/20 rounded-full animate-ping" />
            <div className="w-4 h-4 bg-red-500 rounded-full border-2 border-white shadow-[0_0_15px_rgba(239,68,68,0.8)]" />
          </div>
        </Marker>

        {/* Sample Highlighted Inconsistency 2 */}
        <Marker longitude={37.6173} latitude={55.7558}>
          <div className="relative flex items-center justify-center">
            <div className="absolute w-8 h-8 bg-cyan-500/20 rounded-full animate-ping" />
            <div className="w-4 h-4 bg-cyan-400 rounded-full border-2 border-white shadow-[0_0_15px_rgba(34,211,238,0.8)]" />
          </div>
        </Marker>

      </Map>
    </div>
  );
}
