import { Component, Input } from '@angular/core';
import { CommonModule } from '@angular/common';

export interface RiskCityItem {
  city: string;
  count: number;
  maxMag: number;
  level: 'high' | 'medium' | 'low';
}

@Component({
  selector: 'app-risk-city-list',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './risk-city-list.html',
  styleUrl: './risk-city-list.css'
})
export class RiskCityList {
  @Input() items: RiskCityItem[] = [];
}
