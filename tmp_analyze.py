import pandas as pd

gold = pd.read_parquet(r'data\gold\outlet_features.parquet')
coords_rej = pd.read_parquet(r'data\silver\quarantine\outlet_coordinates_rejected.parquet')
master_rej = pd.read_parquet(r'data\silver\quarantine\outlet_master_rejected.parquet')
bronze_coords = pd.read_csv(r'data\bronze\outlet_coordinates.csv')
bronze_master = pd.read_csv(r'data\bronze\outlet_master.csv')

gold_ids = set(gold['Outlet_ID'])
not_gold = set(bronze_master['Outlet_ID']) - gold_ids
print('Total bronze:', len(bronze_master), ' Gold:', len(gold_ids), ' Not-in-gold:', len(not_gold))

not_gold_coords_rej = coords_rej[coords_rej['Outlet_ID'].isin(not_gold)]
print('Non-gold rejection reasons (first rejection per outlet):')
print(not_gold_coords_rej.drop_duplicates('Outlet_ID')['_rejection_reason'].value_counts())

not_gold_master_rej_ids = set(master_rej['Outlet_ID']) & not_gold
print('Non-gold outlets also in master_rej:', len(not_gold_master_rej_ids))

not_gold_coords = bronze_coords[bronze_coords['Outlet_ID'].isin(not_gold)]
print('Non-gold outlets with bronze coords:', len(not_gold_coords))
print(not_gold_coords[['Outlet_ID','Latitude','Longitude']].head(3).to_string())

# Also check outlet_type for non-gold outlets
not_gold_master = bronze_master[bronze_master['Outlet_ID'].isin(not_gold)]
print('Non-gold outlet types:')
print(not_gold_master['Outlet_Type'].value_counts().head(5))
