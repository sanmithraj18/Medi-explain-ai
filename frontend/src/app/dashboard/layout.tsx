'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { useRouter, usePathname } from 'next/navigation';
import { 
  Activity, LayoutDashboard, Upload, FileText, CreditCard, 
  LogOut, Menu, X, User as UserIcon
} from 'lucide-react';
import { createClient } from '@/lib/supabase/client';
import { toast } from 'sonner';

const navItems = [
  { href: '/dashboard', icon: LayoutDashboard, label: 'Overview' },
  { href: '/dashboard/upload', icon: Upload, label: 'Upload Report' },
  { href: '/dashboard/reports', icon: FileText, label: 'Report History' },
  { href: '/dashboard/billing', icon: CreditCard, label: 'Billing & Plan' },
];

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const [user, setUser] = useState<any>(null);
  const [sidebarOpen, setSidebarOpen] = useState(false);

  useEffect(() => {
    const supabase = createClient();
    supabase.auth.getUser().then(({ data: { user } }) => {
      if (!user) {
        const hasEnv = process.env.NEXT_PUBLIC_SUPABASE_URL;
        if (hasEnv) {
          router.push('/login');
        } else {
          setUser({ email: 'preview@mediexplain.ai', user_metadata: { full_name: 'Dr. Preview User' } });
        }
      } else {
        setUser(user);
      }
    });

    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange((event, session) => {
      if (event === 'SIGNED_OUT') {
        setUser(null);
        router.push('/login');
      } else if (session?.user) {
        setUser(session.user);
      }
    });

    return () => {
      subscription.unsubscribe();
    };
  }, [router]);

  const handleSignOut = async () => {
    const supabase = createClient();
    await supabase.auth.signOut();
    toast.success('Signed out successfully');
    router.push('/');
  };

  return (
    <div className="min-h-screen bg-surface flex">
      {/* Sidebar for Desktop */}
      <aside className={`fixed inset-y-0 left-0 z-50 w-64 bg-white border-r border-slate-100 shadow-sm flex flex-col justify-between transform transition-transform duration-200 lg:translate-x-0 ${sidebarOpen ? 'translate-x-0' : '-translate-x-full'}`}>
        <div>
          {/* Logo */}
          <div className="flex items-center justify-between px-6 h-16 border-b border-slate-100">
            <Link href="/" className="flex items-center gap-2.5">
              <div className="w-8 h-8 bg-gradient-to-br from-teal to-navy rounded-lg flex items-center justify-center">
                <Activity className="text-white" size={18} />
              </div>
              <span className="font-bold text-navy text-base">
                MediExplain <span className="text-teal">AI</span>
              </span>
            </Link>
            <button
              onClick={() => setSidebarOpen(false)}
              className="lg:hidden text-slate-400 hover:text-navy"
            >
              <X size={20} />
            </button>
          </div>

          {/* Navigation Links */}
          <nav className="p-4 space-y-1.5">
            {navItems.map((item) => {
              const active = pathname === item.href;
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  onClick={() => setSidebarOpen(false)}
                  className={`flex items-center gap-3 px-3.5 py-2.5 rounded-xl text-sm font-medium transition-colors ${
                    active
                      ? 'bg-teal/10 text-teal-dark font-semibold'
                      : 'text-blue-grey hover:bg-slate-50 hover:text-navy'
                  }`}
                >
                  <item.icon size={18} className={active ? 'text-teal' : 'text-blue-grey'} />
                  {item.label}
                </Link>
              );
            })}
          </nav>
        </div>

        {/* User Card & Sign Out */}
        <div className="p-4 border-t border-slate-100 space-y-3">
          <div className="bg-slate-50 rounded-xl p-3 flex items-center gap-3">
            <div className="w-9 h-9 rounded-full bg-teal/10 text-teal flex items-center justify-center font-bold text-sm">
              <UserIcon size={16} />
            </div>
            <div className="min-w-0 flex-1">
              <p className="text-xs font-semibold text-navy truncate">
                {user?.user_metadata?.full_name || 'Member'}
              </p>
              <p className="text-[11px] text-blue-grey truncate">
                {user?.email || 'user@mediexplain.ai'}
              </p>
            </div>
          </div>

          <button
            onClick={handleSignOut}
            className="flex items-center gap-2.5 px-3.5 py-2 rounded-lg text-xs font-semibold text-red-600 hover:bg-red-50 w-full transition"
          >
            <LogOut size={16} />
            Sign Out
          </button>
        </div>
      </aside>

      {/* Overlay for mobile sidebar */}
      {sidebarOpen && (
        <div
          className="fixed inset-0 bg-navy/30 z-40 lg:hidden backdrop-blur-xs"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      {/* Main Content Area */}
      <div className="flex-1 flex flex-col min-w-0 lg:pl-64">
        {/* Mobile Header */}
        <header className="bg-white border-b border-slate-100 h-16 flex items-center justify-between px-4 sm:px-6 lg:hidden sticky top-0 z-30">
          <div className="flex items-center gap-3">
            <button
              onClick={() => setSidebarOpen(true)}
              className="p-2 rounded-lg text-navy hover:bg-slate-50"
            >
              <Menu size={22} />
            </button>
            <span className="font-bold text-navy text-base">MediExplain AI</span>
          </div>
          <Link href="/dashboard/upload" className="btn-primary !py-1.5 !px-3 text-xs">
            <Upload size={14} /> Upload
          </Link>
        </header>

        {/* Page Content */}
        <main className="flex-1 p-4 sm:p-6 lg:p-8 max-w-7xl w-full mx-auto">
          {children}
        </main>
      </div>
    </div>
  );
}
