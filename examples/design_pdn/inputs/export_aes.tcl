set here [file dirname [file normalize [info script]]]
cd $here
read_lef Nangate45.lef
read_def Nangate45_data_aes.def
read_liberty Nangate45_typ.lib
read_sdc Nangate45_data_aes.sdc
check_power_grid -net VDD -dont_require_terminals
analyze_power_grid -vsrc Vsrc_aes_vdd.loc -net VDD -enable_em -em_outfile aes_em.csv -voltage_file aes_voltage.csv
write_pg_spice -vsrc Vsrc_aes_vdd.loc -net VDD aes_export.sp
exit
