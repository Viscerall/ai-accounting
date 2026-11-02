-- Dummy Chart of Accounts untuk kafe / restoran
-- Sesuai skema di PDF Brainstorming. Nanti sesuaikan dengan COA asli dari Accurate.

insert into chart_of_accounts (account_code, account_name, account_type, normal_balance, description) values
  ('1100', 'Kas',                                  'ASSET',     'DEBIT',   'Uang tunai di laci kasir / safe'),
  ('1110', 'Kas di Bank (BCA)',                    'ASSET',     'DEBIT',   'Rekening utama kafe (BCA)'),
  ('1120', 'Piutang Settlement QRIS',              'ASSET',     'DEBIT',   'Uang bersih QRIS belum masuk bank (net, after MDR)'),
  ('1121', 'Piutang Settlement EDC',               'ASSET',     'DEBIT',   'Uang bersih EDC belum masuk bank (net, after MDR)'),
  ('1200', 'Persediaan Bahan Baku',                'ASSET',     'DEBIT',   'Stok bahan baku & HPP'),
  ('2100', 'Utang Pajak PB1',                      'LIABILITY', 'CREDIT',  'Pajak Barang/Jasa (Restoran) yang belum dibayar'),
  ('2110', 'Utang Service Charge',                 'LIABILITY', 'CREDIT',  'Service charge yang belum dibayarkan'),
  ('3100', 'Modal Pemilik',                        'EQUITY',    'CREDIT',  'Modal pemilik kafe'),
  ('4100', 'Pendapatan Penjualan',                 'REVENUE',   'CREDIT',  'Pendapatan penjualan makanan & minuman'),
  ('4110', 'Pendapatan Service Charge',            'REVENUE',   'CREDIT',  'Pendapatan dari service charge'),
  ('5100', 'Harga Pokok Penjualan',                 'COGS',      'DEBIT',   'HPP / bahan baku terpakai'),
  ('6100', 'Beban MDR / Payment Gateway',          'EXPENSE',   'DEBIT',   'Biaya fee QRIS (0,7%) / MDR EDC'),
  ('6110', 'Beban Gaji & Tunjangan',               'EXPENSE',   'DEBIT',   'Gaji karyawan, tips, bonus'),
  ('6120', 'Beban Sewa',                           'EXPENSE',   'DEBIT',   'Sewa tempat / peralatan'),
  ('6130', 'Beban Utilitas',                       'EXPENSE',   'DEBIT',   'Listrik, air, gas, internet'),
  ('6140', 'Beban Operasional Lainnya',             'EXPENSE',   'DEBIT',   'Biaya promosi, maintenance, dll.');

-- Cek hasil
select account_code, account_name, account_type, normal_balance
from chart_of_accounts
order by account_code;