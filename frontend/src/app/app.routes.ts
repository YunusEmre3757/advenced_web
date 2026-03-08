import { Routes } from '@angular/router';
import { Dashboard } from './pages/dashboard/dashboard';
import { Map } from './pages/map/map';
import { RiskQuery } from './pages/risk-query/risk-query';

export const routes: Routes = [
    { path: '', redirectTo: 'dashboard', pathMatch: 'full' },
    { path: 'dashboard', component: Dashboard },
    { path: 'map', component: Map },
    { path: 'risk-query', component: RiskQuery },
    { path: '**', redirectTo: 'dashboard' } // Bilinmeyen linkte ana sayfaya dön
];
