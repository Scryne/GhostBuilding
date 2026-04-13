import { ImageResponse } from 'next/og';
import { NextRequest } from 'next/server';

export const runtime = 'edge';

export async function GET(request: NextRequest) {
  try {
    const { searchParams } = new URL(request.url);

    // Extract anomaly details from query string, or provide defaults
    const id = searchParams.get('id');
    const category = searchParams.get('category') || 'MAP_ANOMALY';
    const score = searchParams.get('score') || '0';
    const lat = searchParams.get('lat') || 'Unknown';
    const lng = searchParams.get('lng') || 'Unknown';

    if (!id) {
        // Fallback OG image if no ID is provided
        return new ImageResponse(
            (
                <div
                    style={{
                        height: '100%',
                        width: '100%',
                        display: 'flex',
                        flexDirection: 'column',
                        alignItems: 'center',
                        justifyContent: 'center',
                        backgroundColor: '#0A0E1A',
                        backgroundImage: 'radial-gradient(circle at center, #1E293B 0%, #0A0E1A 100%)',
                        color: 'white',
                    }}
                >
                    <div style={{ fontSize: 80, fontWeight: 800, letterSpacing: '-0.02em', backgroundImage: 'linear-gradient(to right, #4facfe 0%, #00f2fe 100%)', backgroundClip: 'text', color: 'transparent' }}>
                        GhostBuilding
                    </div>
                    <div style={{ fontSize: 40, marginTop: 20, color: '#94A3B8' }}>
                        Global Map Intelligence
                    </div>
                </div>
            ),
            {
                width: 1200,
                height: 630,
            }
        );
    }

    // Dynamic OG Image for Anomaly
    const confidenceColor = parseInt(score) > 80 ? '#34D399' : parseInt(score) > 50 ? '#FBBF24' : '#F87171';

    return new ImageResponse(
      (
        <div
          style={{
            height: '100%',
            width: '100%',
            display: 'flex',
            flexDirection: 'row',
            alignItems: 'flex-start',
            justifyContent: 'space-between',
            backgroundColor: '#0A0E1A',
            color: 'white',
            padding: 60,
          }}
        >
            <div style={{ display: 'flex', flexDirection: 'column', justifyContent: 'space-between', height: '100%', flex: 1 }}>
                <div style={{ display: 'flex', flexDirection: 'column' }}>
                    <div style={{ display: 'flex', alignItems: 'center' }}>
                        <div style={{ width: 16, height: 16, borderRadius: '50%', backgroundColor: confidenceColor, marginRight: 16 }} />
                        <span style={{ fontSize: 32, fontWeight: 600, color: confidenceColor, letterSpacing: '0.1em' }}>
                            {category.replace(/_/g, ' ')}
                        </span>
                    </div>
                    
                    <h1 style={{ fontSize: 72, fontWeight: 800, marginTop: 40, lineHeight: 1.1, color: '#F8FAFC' }}>
                        Geospatial Anomaly Detected
                    </h1>
                    
                    <div style={{ display: 'flex', fontSize: 36, color: '#94A3B8', marginTop: 40 }}>
                        Coordinates: {lat}, {lng}
                    </div>
                </div>

                <div style={{ display: 'flex', alignItems: 'center', fontSize: 32, color: '#475569' }}>
                    <span style={{ borderBottom: '2px solid #6366f1', paddingBottom: 4 }}>
                        ghostbuilding.dev
                    </span>
                </div>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', justifyContent: 'center', height: '100%', width: 300 }}>
                <div style={{ fontSize: 140, fontWeight: 900, color: confidenceColor, lineHeight: 1 }}>
                    {score}
                </div>
                <div style={{ fontSize: 32, color: '#94A3B8', marginTop: 16 }}>
                    Confidence Score
                </div>
            </div>
        </div>
      ),
      {
        width: 1200,
        height: 630,
      }
    );
  } catch (e) {
    console.error(e);
    return new Response(`Failed to generate the image`, {
      status: 500,
    });
  }
}
