import { renderLogin, initLogin } from './pages/login.js';
import { renderRegister, initRegister } from './pages/register.js';
// import { renderDashboard, initDashboard } from './pages/dashboard.js';

const routes = {
  '/': { render: renderLogin, init: initLogin },
  '/login': { render: renderLogin, init: initLogin },
  '/register': { render: renderRegister, init: initRegister },
//   '/dashboard': { render: renderDashboard, init: initDashboard },
};

export function navigate(path) {
  window.history.pushState({}, '', path);
  loadRoute(path);
}

function loadRoute(path) {
  const route = routes[path] || routes['/'];
  app.innerHTML = route.render();
  route.init();  // attach events after DOM is ready
}

window.addEventListener('popstate', () => loadRoute(window.location.pathname));

document.addEventListener('click', (e) => {
  if (e.target.matches('[data-link]')) {
    e.preventDefault();
    navigate(e.target.getAttribute('href'));
  }
});

loadRoute(window.location.pathname);