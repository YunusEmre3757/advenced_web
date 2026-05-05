import { CommonModule } from '@angular/common';
import { Component, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';

import {
  McpApi,
  McpDemoResponse,
  McpToolDef,
  McpToolParam,
  MCP_TOOLS,
} from '../../core/mcp-api';

@Component({
  selector: 'app-mcp-demo',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './mcp-demo.html',
  styleUrl: './mcp-demo.css',
})
export class McpDemoPage {
  private readonly api = inject(McpApi);

  readonly tools = MCP_TOOLS;
  readonly selectedToolName = signal<string>(MCP_TOOLS[0].name);
  readonly argValues = signal<Record<string, unknown>>({});

  readonly loading = signal(false);
  readonly error = signal<string | null>(null);
  readonly response = signal<McpDemoResponse | null>(null);

  // Derived
  readonly selectedTool = computed<McpToolDef>(
    () => this.tools.find(t => t.name === this.selectedToolName()) ?? this.tools[0]
  );

  readonly records = computed<unknown[]>(() => {
    const result = this.response()?.result ?? {};
    return (result['records'] as unknown[]) ?? [];
  });

  readonly strongest = computed(() => {
    const result = this.response()?.result ?? {};
    return (result['strongest'] as Record<string, unknown>) ?? null;
  });

  readonly toolCount = computed(() => this.response()?.tools.length ?? 0);

  readonly resultSummary = computed(() => {
    const result = this.response()?.result ?? {};
    return (result['summary'] as string) ?? '';
  });

  readonly resultKeys = computed(() => {
    const result = this.response()?.result ?? {};
    return Object.keys(result).filter(k => k !== 'records' && k !== 'geojson');
  });

  constructor() {
    this.selectTool(MCP_TOOLS[0].name);
    this.runDemo();
  }

  selectTool(name: string): void {
    this.selectedToolName.set(name);
    const tool = this.tools.find(t => t.name === name);
    if (!tool) return;
    const defaults: Record<string, unknown> = {};
    for (const p of tool.params) {
      defaults[p.name] = p.default;
    }
    this.argValues.set(defaults);
    this.response.set(null);
    this.error.set(null);
  }

  setArg(name: string, value: unknown): void {
    this.argValues.update(prev => ({ ...prev, [name]: value }));
  }

  runDemo(): void {
    if (this.loading()) return;
    this.loading.set(true);
    this.error.set(null);

    this.api.runDemo({
      toolName: this.selectedToolName(),
      arguments: this.argValues(),
    }).subscribe({
      next: res => {
        this.response.set(res);
        this.loading.set(false);
      },
      error: () => {
        this.error.set('MCP demo çalıştırılamadı. Spring backend ve graph servisini kontrol et.');
        this.loading.set(false);
      },
    });
  }

  formatSchema(value: unknown): string {
    return JSON.stringify(value ?? {}, null, 2);
  }

  formatJson(value: unknown): string {
    return JSON.stringify(value, null, 2);
  }

  formatTime(value?: string): string {
    if (!value) return '-';
    return new Intl.DateTimeFormat('tr-TR', {
      day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit',
    }).format(new Date(value));
  }

  asRecord(value: unknown): Record<string, unknown> {
    return (value as Record<string, unknown>) ?? {};
  }

  isEarthquakeList(): boolean {
    const r = this.records();
    return r.length > 0 && typeof (r[0] as Record<string, unknown>)['magnitude'] !== 'undefined';
  }

  trackByTool(_: number, t: McpToolDef): string { return t.name; }
  trackByParam(_: number, p: McpToolParam): string { return p.name; }
  trackByKey(_: number, k: string): string { return k; }
  trackByIndex(i: number): number { return i; }
}
