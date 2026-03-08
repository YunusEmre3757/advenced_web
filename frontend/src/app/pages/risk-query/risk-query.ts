import { Component } from '@angular/core';
import { Router } from '@angular/router';

@Component({
  selector: 'app-risk-query',
  imports: [],
  templateUrl: './risk-query.html',
  styleUrl: './risk-query.css',
})
export class RiskQuery {
  constructor(private router: Router) { }
  goBack() {
    this.router.navigate(['/']);
  }
}
