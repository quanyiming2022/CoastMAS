import {afterEach, it, expect, vi} from 'vitest';
import {cleanup, render, screen, fireEvent} from '@testing-library/react';
import {QueryClient, QueryClientProvider} from '@tanstack/react-query';
import {ManagedCatalog} from './ManagedCatalog';
vi.mock('./api',()=>({api:vi.fn(async()=>({items:[{id:'a',name:'a@example.test',revision:0,state:'active',classification:'',status:'active',updated:0,email:'a@example.test',system_admin:false,project_count:0}],total:1}))}));
afterEach(cleanup);
it('cannot select stale rows while the entered filter has not reached the server',async()=>{
 render(<QueryClientProvider client={new QueryClient({defaultOptions:{queries:{retry:false}}})}><ManagedCatalog kind="users" project="p" /></QueryClientProvider>);
 await screen.findByRole('cell',{name:'a@example.test'});
 fireEvent.change(screen.getByLabelText('搜索用户管理'),{target:{value:'different'}});
 expect(screen.getByLabelText('全选本页')).toBeDisabled();
 expect(screen.getByRole('button',{name:'全选筛选结果'})).toBeDisabled();
});
