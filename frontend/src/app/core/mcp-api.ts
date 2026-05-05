import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';

// ---------------------------------------------------------------------------
// Tool registry — mirrors seismic_server.py tools
// ---------------------------------------------------------------------------

export interface McpToolParam {
  name: string;
  type: 'number' | 'string' | 'boolean';
  default: number | string | boolean;
  label: string;
  min?: number;
  max?: number;
  step?: number;
  options?: string[];
}

export interface McpToolDef {
  name: string;
  label: string;
  description: string;
  params: McpToolParam[];
}

export const MCP_TOOLS: McpToolDef[] = [
  {
    name: 'get_recent_earthquakes',
    label: 'Son Depremler',
    description: 'Spring backend\'den son depremleri getirir.',
    params: [
      { name: 'hours', type: 'number', default: 24, label: 'Saat', min: 1, max: 168 },
      { name: 'min_magnitude', type: 'number', default: 1.0, label: 'Min Magnitüd', min: 0, max: 10, step: 0.1 },
      { name: 'limit', type: 'number', default: 8, label: 'Limit', min: 1, max: 20 },
    ],
  },
  {
    name: 'get_seismic_context',
    label: 'Sismik Bağlam',
    description: 'Bir nokta etrafındaki son, tarihsel ve fay hattı bağlamını döndürür.',
    params: [
      { name: 'latitude', type: 'number', default: 41.015, label: 'Enlem', step: 0.001 },
      { name: 'longitude', type: 'number', default: 28.979, label: 'Boylam', step: 0.001 },
      { name: 'radius_km', type: 'number', default: 100, label: 'Yarıçap (km)', min: 10, max: 300 },
    ],
  },
  {
    name: 'get_earthquake_detail',
    label: 'Deprem Detayı',
    description: 'Bir deprem olayının tam zenginleştirmesini getirir (artçılar, benzer, dyfi, shakemap).',
    params: [
      { name: 'event_id', type: 'string', default: 'us7000m9g4', label: 'Event ID' },
    ],
  },
  {
    name: 'get_historical_events',
    label: 'Tarihsel Olaylar',
    description: 'Spring backend\'den tarihsel deprem olaylarını döndürür.',
    params: [
      { name: 'years', type: 'number', default: 50, label: 'Yıl', min: 1, max: 100 },
      { name: 'min_magnitude', type: 'number', default: 4.5, label: 'Min Magnitüd', min: 0, max: 10, step: 0.1 },
    ],
  },
  {
    name: 'assess_building_risk',
    label: 'Bina Risk Değerlendirmesi',
    description: 'Deterministik yapısal + sismik risk skoru hesaplar (LLM yok).',
    params: [
      { name: 'latitude', type: 'number', default: 41.015, label: 'Enlem', step: 0.001 },
      { name: 'longitude', type: 'number', default: 28.979, label: 'Boylam', step: 0.001 },
      { name: 'construction_year', type: 'number', default: 1990, label: 'İnşaat Yılı', min: 1800, max: 2025 },
      { name: 'floor_count', type: 'number', default: 5, label: 'Kat Sayısı', min: 1, max: 50 },
      { name: 'soil_type', type: 'string', default: 'ZC', label: 'Zemin Sınıfı', options: ['ZA', 'ZB', 'ZC', 'ZD', 'ZE', 'ZF'] },
      { name: 'structural_system', type: 'string', default: 'RC', label: 'Yapı Sistemi', options: ['RC', 'URM', 'S'] },
      { name: 'visible_damage', type: 'boolean', default: false, label: 'Görünür Hasar' },
    ],
  },
];

// ---------------------------------------------------------------------------
// API types
// ---------------------------------------------------------------------------

export interface McpDemoRequest {
  toolName: string;
  arguments: Record<string, unknown>;
}

export interface McpDemoStep {
  name: string;
  label: string;
  status: 'ok' | 'error' | 'empty' | string;
  detail: string;
}

export interface McpDemoTool {
  name: string;
  title?: string | null;
  description?: string | null;
  inputSchema?: Record<string, unknown>;
  outputSchema?: Record<string, unknown> | null;
}

export interface McpDemoResponse {
  transport: string;
  endpoint: string;
  server: {
    name: string;
    version: string;
    protocolVersion: string;
    instructions?: string | null;
  };
  steps: McpDemoStep[];
  tools: McpDemoTool[];
  selectedTool: string;
  arguments: Record<string, unknown>;
  result: Record<string, unknown>;
  stderr?: string;
  explanation: string[];
}

// ---------------------------------------------------------------------------
// Service
// ---------------------------------------------------------------------------

@Injectable({ providedIn: 'root' })
export class McpApi {
  private readonly http = inject(HttpClient);
  private readonly graphMcpDemoUrl = 'http://localhost:8080/api/graph/mcp-demo';

  runDemo(payload: McpDemoRequest): Observable<McpDemoResponse> {
    return this.http.post<McpDemoResponse>(this.graphMcpDemoUrl, payload);
  }
}
