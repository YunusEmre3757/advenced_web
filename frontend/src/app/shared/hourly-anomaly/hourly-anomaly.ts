import { Component, Input } from '@angular/core';
import { CommonModule } from '@angular/common';

export interface HourlyPoint {
  hour: string;
  count: number;
}

@Component({
  selector: 'app-hourly-anomaly',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './hourly-anomaly.html',
  styleUrl: './hourly-anomaly.css'
})
export class HourlyAnomaly {
  @Input() series: HourlyPoint[] = [];
  @Input() latest = 0;
  @Input() baseline = 0;
  @Input() level: 'high' | 'medium' | 'low' = 'low';
  @Input() message = '';

  get maxValue(): number {
    return Math.max(1, ...this.series.map(s => s.count));
  }

  barClass(value: number): string {
    const ratio = value / this.maxValue;
    if (ratio >= 0.72) return 'bar--high';
    if (ratio >= 0.42) return 'bar--mid';
    return 'bar--low';
  }
}
