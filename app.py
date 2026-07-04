import streamlit as st
import pandas as pd
import re
import io
import zipfile

# Page Configuration matching layout
st.set_page_config(page_title="Secure Beneficiary Data Segregator", layout="wide")

st.title("🛡️ Secure GP-Wise Beneficiary Segregator")
st.caption("Data Privacy Guard: All data is processed entirely inside your browser memory and is never transmitted to backend disks.")
st.markdown("---")

# Helper function to aggressively wipe out any hidden characters/non-breaking spaces
def clean_string(val):
    if pd.isna(val):
        return ""
    return re.sub(r'[\s\xa0]+', ' ', str(val)).strip()

def process_dataframe(uploaded_file):
    if uploaded_file is None:
        return None
    try:
        df = pd.read_csv(uploaded_file, sep=None, engine='python')
        
        # 1. Clean all column headers dynamically
        df.columns = [clean_string(c) for c in df.columns]
        
        # 2. Clean all data values dynamically across the entire dataset
        for col in df.columns:
            if df[col].dtype == 'object':
                df[col] = df[col].apply(clean_string)
                
        # Remap layout column variants dynamically
        col_mapping = {
            'SubDistrict/ Municipality': 'SubDistrict',
            'Sub-District / Municipality': 'SubDistrict',
            'Gram Panchayat/Ward': 'Gram_Panchayat',
            'Gram Panchayat': 'Gram_Panchayat',
            'Village': 'Village',
            'Applicant Name': 'Applicant_Name',
            'Scheme': 'Scheme',
            'Aadhar No': 'Aadhaar_Status'
        }
        df = df.rename(columns=lambda x: col_mapping.get(x, x))
        
        # Standardize Aadhaar status values cleanly
        df['Aadhaar_Status'] = df['Aadhaar_Status'].map(lambda x: 'No' if str(x).lower() in ['no', '0', 'false', 'n'] else 'Yes')
        return df
    except Exception as e:
        st.error(f"Error reading file: {e}")
        return None

# Sidebar Navigation Panel
st.sidebar.header("📂 Data Ingestion & Control")
current_file = st.sidebar.file_uploader("Upload Current Month CSV", type=["csv"], key="current_month")
prior_file = st.sidebar.file_uploader("Upload Prior Month CSV (Optional for Comparisons)", type=["csv"], key="prior_month")

if current_file is not None:
    df_current = process_dataframe(current_file)
    df_prior = process_dataframe(prior_file) if prior_file is not None else None
    
    required = ['SubDistrict', 'Gram_Panchayat', 'Applicant_Name', 'Scheme', 'Aadhaar_Status']
    missing = [r for r in required if r not in df_current.columns]
    
    if missing:
        st.error(f"Missing required columns in CSV: {missing}. Found columns: {list(df_current.columns)}")
    else:
        # --- GLOBAL SIDEBAR FILTERS ---
        st.sidebar.markdown("---")
        st.sidebar.header("🎯 Filter Options")
        
        all_subdistricts = sorted(df_current['SubDistrict'].dropna().unique().tolist())
        selected_subdistricts = st.sidebar.multiselect("Select Sub-District / Municipality", options=all_subdistricts, default=all_subdistricts)
        
        all_schemes = sorted(df_current['Scheme'].dropna().unique().tolist())
        selected_schemes = st.sidebar.multiselect("Select Schemes for Matrix/Lists", options=all_schemes, default=all_schemes)
        
        all_gps = sorted(df_current['Gram_Panchayat'].dropna().unique().tolist())
        selected_gp = st.sidebar.selectbox("Select Gram Panchayat / Ward (GP)", options=["All GPs"] + all_gps)

        # Base scoped data based on global location configurations
        df_curr_scoped = df_current[df_current['SubDistrict'].isin(selected_subdistricts)]
        if selected_gp != "All GPs":
            df_curr_scoped = df_curr_scoped[df_curr_scoped['Gram_Panchayat'] == selected_gp]

        # Layout Navigation Tabs
        tab1, tab2, tab3, tab4 = st.tabs([
            "📊 Seeding PERCENTAGE", 
            "🔄 Monthly Comparison ", 
            "📋 AADHAR SEEDED - NON SEEDED REPORT", 
            "🔍 DOWNLOAD TAB"
        ])

        # Global analytical extraction logic so tables can be exported dynamically downstream
        def generate_performance_table(data_frame):
            if data_frame.empty:
                return pd.DataFrame()
            stats = data_frame.groupby('Gram_Panchayat').agg(
                Total_Applicants=('Applicant_Name', 'count'),
                Aadhaar_Seeded=('Aadhaar_Status', lambda x: (x == 'Yes').sum())
            ).reset_index()
            
            stats['Aadhaar Seeding %'] = (stats['Aadhaar_Seeded'] / stats['Total_Applicants'] * 100).round(2)
            
            total_row = pd.DataFrame([{
                'Gram_Panchayat': 'TOTAL',
                'Total_Applicants': stats['Total_Applicants'].sum(),
                'Aadhaar_Seeded': stats['Aadhaar_Seeded'].sum(),
                'Aadhaar Seeding %': round((stats['Aadhaar_Seeded'].sum() / stats['Total_Applicants'].sum() * 100), 2) if stats['Total_Applicants'].sum() > 0 else 0
            }])
            stats = pd.concat([stats, total_row], ignore_index=True)
            stats.columns = ['Gram Panchayat / Ward', 'Total Applicants', 'Aadhaar Seeded', 'Aadhaar Seeding %']
            return stats

        state_df = df_curr_scoped[df_curr_scoped['Scheme'].str.contains('OAPFSC', case=False, na=False)]
        state_table = generate_performance_table(state_df)

        central_df = df_curr_scoped[df_curr_scoped['Scheme'].str.contains('IGN', case=False, na=False)]
        central_table = generate_performance_table(central_df)

        # --- TAB 1: SEEDING PERFORMANCE ---
        with tab1:
            st.subheader("Performance Analysis Templates")
            
            st.markdown("### State Scheme View (OAPFSC)")
            if not state_table.empty:
                st.dataframe(state_table, width='stretch', hide_index=True)
            else:
                st.info("No OAPFSC Scheme entries found matching your selected location parameters.")
                
            st.markdown("### Central Schemes View (IGNOAPS, IGNWPS, IGNDPS)")
            if not central_table.empty:
                st.dataframe(central_table, width='stretch', hide_index=True)
            else:
                st.info("No Central Scheme entries found matching your selected location parameters.")

        # --- TAB 2: MONTHLY COMPARISON ---
        with tab2:
            st.subheader("Performance Comparison")
            if df_prior is None:
                st.info("ℹ️ Please upload a prior month CSV file in the sidebar to populate this dashboard comparison view automatically.")
            else:
                df_curr_comp = df_curr_scoped[df_curr_scoped['Scheme'].isin(selected_schemes)]
                curr_grp = df_curr_comp.groupby('Gram_Panchayat').agg(
                    Total_C=('Applicant_Name', 'count'),
                    Seeded_C=('Aadhaar_Status', lambda x: (x == 'Yes').sum()),
                    NotSeeded_C=('Aadhaar_Status', lambda x: (x == 'No').sum())
                )
                
                df_prior_filtered = df_prior[df_prior['SubDistrict'].isin(selected_subdistricts) & df_prior['Scheme'].isin(selected_schemes)]
                if selected_gp != "All GPs":
                    df_prior_filtered = df_prior_filtered[df_prior_filtered['Gram_Panchayat'] == selected_gp]
                    
                prior_grp = df_prior_filtered.groupby('Gram_Panchayat').agg(
                    Total_P=('Applicant_Name', 'count'),
                    Seeded_P=('Aadhaar_Status', lambda x: (x == 'Yes').sum()),
                    NotSeeded_P=('Aadhaar_Status', lambda x: (x == 'No').sum())
                )
                
                comp = curr_grp.join(prior_grp, how='outer').fillna(0).astype(int).reset_index()
                comp['Changes_T'] = comp['Total_C'] - comp['Total_P']
                comp['Changes_S'] = comp['Seeded_C'] - comp['Seeded_P']
                comp['Changes_N'] = comp['NotSeeded_C'] - comp['NotSeeded_P']
                
                ordered_cols = ['Gram_Panchayat', 'Total_P', 'Total_C', 'Changes_T', 'Seeded_P', 'Seeded_C', 'Changes_S', 'NotSeeded_P', 'NotSeeded_C', 'Changes_N']
                comp_final = comp[ordered_cols]
                
                t_row = pd.DataFrame([{
                    'Gram_Panchayat': 'TOTAL',
                    'Total_P': comp_final['Total_P'].sum(), 'Total_C': comp_final['Total_C'].sum(), 'Changes_T': comp_final['Changes_T'].sum(),
                    'Seeded_P': comp_final['Seeded_P'].sum(), 'Seeded_C': comp_final['Seeded_C'].sum(), 'Changes_S': comp_final['Changes_S'].sum(),
                    'NotSeeded_P': comp_final['NotSeeded_P'].sum(), 'NotSeeded_C': comp_final['NotSeeded_C'].sum(), 'Changes_N': comp_final['Changes_N'].sum()
                }])
                comp_final = pd.concat([comp_final, t_row], ignore_index=True)
                comp_final.columns = ['GP Name', 'TOTAL (PRIOR)', 'TOTAL (CURRENT)', 'TOTAL (CHANGES)', 'SEEDED (PRIOR)', 'SEEDED (CURRENT)', 'SEEDED (CHANGES)', 'NOT SEEDED (PRIOR)', 'NOT SEEDED (CURRENT)', 'NOT SEEDED (CHANGES)']
                st.dataframe(comp_final, width='stretch', hide_index=True)

        # --- TAB 3: GP-WISE SCHEME CROSS-TAB MATRIX ---
        matrix_flat = pd.DataFrame()
        with tab3:
            st.subheader("GP-Wise Scheme Distribution Matrix")
            df_matrix_source = df_curr_scoped[df_curr_scoped['Scheme'].isin(selected_schemes)]
            
            if not df_matrix_source.empty:
                matrix_pivot = df_matrix_source.groupby(['Gram_Panchayat', 'Scheme', 'Aadhaar_Status']).size().unstack(fill_value=0).reset_index()
                for status_col in ['Yes', 'No']:
                    if status_col not in matrix_pivot.columns:
                        matrix_pivot[status_col] = 0
                        
                matrix_flat = matrix_pivot.pivot(index='Gram_Panchayat', columns='Scheme', values=['Yes', 'No']).fillna(0).astype(int)
                matrix_flat.columns = [f"{col[1]} - {'Seeded' if col[0] == 'Yes' else 'Not Seeded'}" for col in matrix_flat.columns]
                matrix_flat = matrix_flat.reset_index()
                
                grand_totals = {'Gram_Panchayat': 'GRAND TOTAL'}
                for num_col in matrix_flat.columns:
                    if num_col != 'Gram_Panchayat':
                        grand_totals[num_col] = matrix_flat[num_col].sum()
                        
                matrix_flat = pd.concat([matrix_flat, pd.DataFrame([grand_totals])], ignore_index=True)
                matrix_flat = matrix_flat.rename(columns={'Gram_Panchayat': 'Gram Panchayat'})
                st.dataframe(matrix_flat, width='stretch', hide_index=True)
            else:
                st.info("No data available for the selected filters.")

        # --- TAB 4: GRANULAR LISTS & CUSTOM EXPORT STRUCTURING ---
        with tab4:
            st.subheader("Filter-Driven Custom Records Extraction & Export Center")
            
            status_filter = st.radio("Target Seeding Group", options=["All Beneficiaries", "Seeded Only (Yes)", "Non-Seeded Only (No)"])
            output_df = df_curr_scoped[df_curr_scoped['Scheme'].isin(selected_schemes)].copy()
            if status_filter == "Seeded Only (Yes)":
                output_df = output_df[output_df['Aadhaar_Status'] == 'Yes']
            elif status_filter == "Non-Seeded Only (No)":
                output_df = output_df[output_df['Aadhaar_Status'] == 'No']
                
            display_cols = [c for c in ['SubDistrict', 'Gram_Panchayat', 'Village', 'Applicant_Name', 'Scheme', 'Aadhaar_Status'] if c in output_df.columns]
            filtered_data_to_show = output_df[display_cols]
            st.dataframe(filtered_data_to_show, width='stretch', hide_index=True)
            
            st.markdown("---")
            st.markdown("### 🗂️ Compilation Preferences")
            
            # Feature choice implementation requested by user
            export_mode = st.radio("Do you need all results in the same Excel file?", options=["Yes", "No"], horizontal=True)
            
            if export_mode == "Yes":
                # Combined Multi-Sheet Workbook Generation
                single_excel_buffer = io.BytesIO()
                with pd.ExcelWriter(single_excel_buffer, engine='openpyxl') as writer:
                    filtered_data_to_show.to_excel(writer, index=False, sheet_name='Filtered Records Extraction')
                    if not state_table.empty:
                        state_table.to_excel(writer, index=False, sheet_name='State Performance (OAPFSC)')
                    if not central_table.empty:
                        central_table.to_excel(writer, index=False, sheet_name='Central Performance (IGN)')
                    if not matrix_flat.empty:
                        matrix_flat.to_excel(writer, index=False, sheet_name='Cross-Tab Matrix View')
                
                st.download_button(
                    label="📥 Download Single Combined Workspace (Excel XLSX Sheets)",
                    data=single_excel_buffer.getvalue(),
                    file_name="combined_beneficiary_consolidated_report.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
                
            else:
                # Disjointed Reports packed inside a safe ZIP Archive Container
                zip_buffer = io.BytesIO()
                with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
                    
                    # 1. Custom Extract List Sheet
                    f_buffer = io.BytesIO()
                    with pd.ExcelWriter(f_buffer, engine='openpyxl') as writer:
                        filtered_data_to_show.to_excel(writer, index=False)
                    zip_file.writestr("1_custom_filtered_records.xlsx", f_buffer.getvalue())
                    
                    # 2. State Performance
                    if not state_table.empty:
                        s_buffer = io.BytesIO()
                        with pd.ExcelWriter(s_buffer, engine='openpyxl') as writer:
                            state_table.to_excel(writer, index=False)
                        zip_file.writestr("2_state_performance_report.xlsx", s_buffer.getvalue())
                        
                    # 3. Central Performance
                    if not central_table.empty:
                        c_buffer = io.BytesIO()
                        with pd.ExcelWriter(c_buffer, engine='openpyxl') as writer:
                            central_table.to_excel(writer, index=False)
                        zip_file.writestr("3_central_performance_report.xlsx", c_buffer.getvalue())
                        
                    # 4. Matrix distribution
                    if not matrix_flat.empty:
                        m_buffer = io.BytesIO()
                        with pd.ExcelWriter(m_buffer, engine='openpyxl') as writer:
                            matrix_flat.to_excel(writer, index=False)
                        zip_file.writestr("4_crosstab_distribution_matrix.xlsx", m_buffer.getvalue())
                
                st.download_button(
                    label="📥 Download Disjointed Workspace Packages (ZIP Archive Containing Excel files)",
                    data=zip_buffer.getvalue(),
                    file_name="individual_beneficiary_reports_package.zip",
                    mime="application/zip"
                )
else:
    st.info("💡 Please upload your current month beneficiary CSV file using the sidebar panel to generate the dashboard views.")