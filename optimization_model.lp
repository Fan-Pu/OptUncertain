\ Model multi_agent_many_to_many
\ LP format - for model browsing. Use MPS format to capture full model detail.
\ Signature: 0xb9cc449ae2b12c69
Maximize
  - 0.0223050693339395 x_6_76_agent0 - 0.0187588088201864 x_12_50_agent0
   - 0.0111207092521028 x_12_58_agent0 - 0.0145487610820641 x_41_61_agent0
   - 0.0229324846556036 x_41_76_agent0 - 0.0187588088201864 x_50_12_agent0
   - 0.0150761536712889 x_50_58_agent0 - 0.0358354171402592 x_50_76_agent0
   - 0.0203591725392135 x_56_61_agent0 - 0.0111207092521028 x_58_12_agent0
   - 0.0150761536712889 x_58_50_agent0 - 0.0145487610820641 x_61_41_agent0
   - 0.0203591725392135 x_61_56_agent0 - 0.0150852466469652 x_61_76_agent0
   - 0.0223050693339395 x_76_6_agent0 - 0.0229324846556036 x_76_41_agent0
   - 0.0358354171402592 x_76_50_agent0 - 0.0150852466469652 x_76_61_agent0
   + 0.0133333333333333 y_6_agent0 - 0.01 y_12_agent0 + 0.08 y_41_agent0
   - 0.02 y_50_agent0 + 0.1066666666666667 y_56_agent0 - 0.01 y_58_agent0
   - 0.01 y_76_agent0 + 0.2 y_96_agent0 + 0 u_95_agent0 + 0 u_96_agent0
   + 0 u_97_agent0 + 0 u_98_agent0 + 0 u_99_agent0
   + 0.0145487610820641 Constant
Subject To
 depart_agent0: x_61_41_agent0 + x_61_56_agent0 + x_61_76_agent0 = 1
 first_hop_vp_agent0: x_61_41_agent0 + x_61_56_agent0 + x_61_76_agent0 = 1
 first_hop_grounded_vv_agent0: x_61_41_agent0 + x_61_56_agent0
   + x_61_76_agent0 = 1
 no_return_agent0: x_41_61_agent0 + x_56_61_agent0 + x_76_61_agent0 = 0
 flow_in_6_agent0: x_76_6_agent0 - y_6_agent0 = 0
 flow_out_6_agent0: x_6_76_agent0 - y_6_agent0 <= 0
 flow_in_12_agent0: x_50_12_agent0 + x_58_12_agent0 - y_12_agent0 = 0
 flow_out_12_agent0: x_12_50_agent0 + x_12_58_agent0 - y_12_agent0 <= 0
 flow_in_41_agent0: x_61_41_agent0 + x_76_41_agent0 - y_41_agent0 = 0
 flow_out_41_agent0: x_41_61_agent0 + x_41_76_agent0 - y_41_agent0 <= 0
 flow_in_50_agent0: x_12_50_agent0 + x_58_50_agent0 + x_76_50_agent0
   - y_50_agent0 = 0
 flow_out_50_agent0: x_50_12_agent0 + x_50_58_agent0 + x_50_76_agent0
   - y_50_agent0 <= 0
 flow_in_56_agent0: x_61_56_agent0 - y_56_agent0 = 0
 flow_out_56_agent0: x_56_61_agent0 - y_56_agent0 <= 0
 flow_in_58_agent0: x_12_58_agent0 + x_50_58_agent0 - y_58_agent0 = 0
 flow_out_58_agent0: x_58_12_agent0 + x_58_50_agent0 - y_58_agent0 <= 0
 flow_in_76_agent0: x_6_76_agent0 + x_41_76_agent0 + x_50_76_agent0
   + x_61_76_agent0 - y_76_agent0 = 0
 flow_out_76_agent0: x_76_6_agent0 + x_76_41_agent0 + x_76_50_agent0
   + x_76_61_agent0 - y_76_agent0 <= 0
 flow_in_95_agent0: - y_95_agent0 = 0
 flow_out_95_agent0: - y_95_agent0 <= 0
 flow_in_96_agent0: - y_96_agent0 = 0
 flow_out_96_agent0: - y_96_agent0 <= 0
 flow_in_97_agent0: - y_97_agent0 = 0
 flow_out_97_agent0: - y_97_agent0 <= 0
 flow_in_98_agent0: - y_98_agent0 = 0
 flow_out_98_agent0: - y_98_agent0 <= 0
 flow_in_99_agent0: - y_99_agent0 = 0
 flow_out_99_agent0: - y_99_agent0 <= 0
 mtz_6_76_agent0: 13 x_6_76_agent0 + u_6_agent0 - u_76_agent0 <= 12
 mtz_12_50_agent0: 13 x_12_50_agent0 + u_12_agent0 - u_50_agent0 <= 12
 mtz_12_58_agent0: 13 x_12_58_agent0 + u_12_agent0 - u_58_agent0 <= 12
 mtz_41_61_agent0: 13 x_41_61_agent0 + u_41_agent0 - u_61_agent0 <= 12
 mtz_41_76_agent0: 13 x_41_76_agent0 + u_41_agent0 - u_76_agent0 <= 12
 mtz_50_12_agent0: 13 x_50_12_agent0 - u_12_agent0 + u_50_agent0 <= 12
 mtz_50_58_agent0: 13 x_50_58_agent0 + u_50_agent0 - u_58_agent0 <= 12
 mtz_50_76_agent0: 13 x_50_76_agent0 + u_50_agent0 - u_76_agent0 <= 12
 mtz_56_61_agent0: 13 x_56_61_agent0 + u_56_agent0 - u_61_agent0 <= 12
 mtz_58_12_agent0: 13 x_58_12_agent0 - u_12_agent0 + u_58_agent0 <= 12
 mtz_58_50_agent0: 13 x_58_50_agent0 - u_50_agent0 + u_58_agent0 <= 12
 mtz_61_41_agent0: 13 x_61_41_agent0 - u_41_agent0 + u_61_agent0 <= 12
 mtz_61_56_agent0: 13 x_61_56_agent0 - u_56_agent0 + u_61_agent0 <= 12
 mtz_61_76_agent0: 13 x_61_76_agent0 + u_61_agent0 - u_76_agent0 <= 12
 mtz_76_6_agent0: 13 x_76_6_agent0 - u_6_agent0 + u_76_agent0 <= 12
 mtz_76_41_agent0: 13 x_76_41_agent0 - u_41_agent0 + u_76_agent0 <= 12
 mtz_76_50_agent0: 13 x_76_50_agent0 - u_50_agent0 + u_76_agent0 <= 12
 mtz_76_61_agent0: 13 x_76_61_agent0 - u_61_agent0 + u_76_agent0 <= 12
Bounds
 1 <= u_6_agent0 <= 13
 1 <= u_12_agent0 <= 13
 1 <= u_41_agent0 <= 13
 1 <= u_50_agent0 <= 13
 1 <= u_56_agent0 <= 13
 1 <= u_58_agent0 <= 13
 1 <= u_61_agent0 <= 13
 1 <= u_76_agent0 <= 13
 1 <= u_95_agent0 <= 13
 1 <= u_96_agent0 <= 13
 1 <= u_97_agent0 <= 13
 1 <= u_98_agent0 <= 13
 1 <= u_99_agent0 <= 13
 Constant = 1
Binaries
 x_6_76_agent0 x_12_50_agent0 x_12_58_agent0 x_41_61_agent0 x_41_76_agent0
 x_50_12_agent0 x_50_58_agent0 x_50_76_agent0 x_56_61_agent0 x_58_12_agent0
 x_58_50_agent0 x_61_41_agent0 x_61_56_agent0 x_61_76_agent0 x_76_6_agent0
 x_76_41_agent0 x_76_50_agent0 x_76_61_agent0 y_6_agent0 y_12_agent0
 y_41_agent0 y_50_agent0 y_56_agent0 y_58_agent0 y_76_agent0 y_95_agent0
 y_96_agent0 y_97_agent0 y_98_agent0 y_99_agent0
End
