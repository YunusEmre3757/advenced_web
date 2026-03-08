import { Component, Input } from '@angular/core';
import { CommonModule } from '@angular/common';

export interface AiInsightItem {
  title: string;
  text: string;
  severity: 'high' | 'medium' | 'low';
}

@Component({
  selector: 'app-ai-insights',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './ai-insights.html',
  styleUrl: './ai-insights.css'
})
export class AiInsights {
  @Input() items: AiInsightItem[] = [];
}
