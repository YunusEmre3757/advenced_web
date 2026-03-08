import { Component, Input } from '@angular/core';
import { CommonModule } from '@angular/common';

export type KpiAccent = 'blue' | 'red' | 'orange' | 'green' | 'purple';

@Component({
  selector: 'app-kpi-card',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './kpi-card.html',
  styleUrl: './kpi-card.css',
})
export class KpiCard {
  @Input() label = '';
  @Input() value = '';
  @Input() sub = '';
  @Input() accent: KpiAccent = 'blue';
  @Input() delta?: string | null = null; // örn: '+12%', '-3%'
  @Input() deltaDir: 'up' | 'down' | null = null;
}
