set here [file dirname [file normalize [info script]]]
cd $here
read_lef Nangate45.lef
read_def Nangate45_data_gcd.def
read_liberty Nangate45_typ.lib
read_sdc Nangate45_data_gcd.sdc
check_power_grid -net VDD -dont_require_terminals
analyze_power_grid -vsrc Vsrc_gcd_vdd.loc -net VDD -enable_em -em_outfile gcd_em.csv -voltage_file gcd_voltage.csv
write_pg_spice -vsrc Vsrc_gcd_vdd.loc -net VDD gcd_export.sp
exit
