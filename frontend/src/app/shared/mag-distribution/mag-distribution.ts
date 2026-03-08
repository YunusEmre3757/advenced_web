import { Component, Input, computed, signal, OnChanges, SimpleChanges } from '@angular/core';
import { CommonModule } from '@angular/common';

export interface MagDistributionItem {
  label: string;
  count: number;
  percentage: number;
  color: string;
}

interface DonutSegment {
  label: string;
  color: string;
  dashArray: string;
  dashOffset: string;
}

@Component({
  selector: 'app-mag-distribution',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './mag-distribution.html',
  styleUrl: './mag-distribution.css'
})
export class MagDistribution implements OnChanges {
  @Input() data: MagDistributionItem[] = [];

  private readonly dataSignal = signal<MagDistributionItem[]>([]);
  private readonly circumference = 2 * Math.PI * 48; // r=48

  ngOnChanges(changes: SimpleChanges): void {
    if (changes['data']) {
      this.dataSignal.set(this.data);
    }
  }

  readonly total = computed(() => this.dataSignal().reduce((sum, item) => sum + item.count, 0));

  readonly segments = computed<DonutSegment[]>(() => {
    const items = this.dataSignal();
    const t = this.total();
    if (t === 0) return [];

    const C = this.circumference;
    const gap = 4;
    let offset = 0;

    const activeItems = items.filter(item => item.count > 0);

    return activeItems.map(item => {
      const pct = item.count / t;
      const segLen = Math.max(pct * C - gap, 2);
      const seg: DonutSegment = {
        label: item.label,
        color: item.color,
        dashArray: `${segLen} ${C - segLen}`,
        dashOffset: `${-offset}`
      };
      offset += pct * C;
      return seg;
    });
  });
}
