import { Component, inject } from '@angular/core';
import { Router, RouterLink, RouterLinkActive } from '@angular/router';

import { AuthApi } from '../../core/auth-api';

@Component({
  selector: 'app-navbar',
  imports: [RouterLink, RouterLinkActive],
  templateUrl: './navbar.html',
  styleUrl: './navbar.css',
})
export class Navbar {
  private readonly auth = inject(AuthApi);
  private readonly router = inject(Router);

  readonly user = this.auth.user;
  readonly isAuthenticated = this.auth.isAuthenticated;

  logout(): void {
    this.auth.logout();
    this.router.navigate(['/login']);
  }
}
