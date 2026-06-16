\ Model multi_agent_many_to_many
\ LP format - for model browsing. Use MPS format to capture full model detail.
\ Signature: 0x68edb04c9b0930a7
Maximize multi-objectives
  target_directed_reward: Priority=2 Weight=1 AbsTol=0 RelTol=0
   0 u_50_agent0 + 0 u_51_agent0 + 0 u_52_agent0 + 0 u_53_agent0
   + 0 u_55_agent0 + 0 u_56_agent0 + 0 u_50_agent1 + 0 u_51_agent1
   + 0 u_52_agent1 + 0 u_53_agent1 + 0 u_55_agent1 + 0 u_56_agent1
   + 0.35 z_2_0_agent0 + 0.35 z_3_0_agent0 + 0.15 z_2_6_agent0
   + 0.15 z_3_6_agent0 + 0.08 z_2_14_agent0 + 0.08 z_3_14_agent0
   + 0.05 z_2_19_agent0 + 0.05 z_3_19_agent0 + 0.08 z_2_21_agent0
   + 0.08 z_3_21_agent0 + 0.05 z_2_23_agent0 + 0.05 z_3_23_agent0
   + 0.08 z_2_27_agent0 + 0.08 z_3_27_agent0 + 0.08 z_2_35_agent0
   + 0.08 z_3_35_agent0 + 0.08 z_2_43_agent0 + 0.08 z_3_43_agent0
   + 0.08 z_2_46_agent0 + 0.08 z_3_46_agent0 + 0.05 z_2_48_agent0
   + 0.05 z_3_48_agent0 + 0.9 z_2_54_agent0 + 0.9 z_3_54_agent0
   + 0.35 z_2_0_agent1 + 0.35 z_3_0_agent1 + 0.15 z_2_6_agent1
   + 0.15 z_3_6_agent1 + 0.08 z_2_14_agent1 + 0.08 z_3_14_agent1
   + 0.05 z_2_19_agent1 + 0.05 z_3_19_agent1 + 0.08 z_2_21_agent1
   + 0.08 z_3_21_agent1 + 0.05 z_2_23_agent1 + 0.05 z_3_23_agent1
   + 0.08 z_2_27_agent1 + 0.08 z_3_27_agent1 + 0.08 z_2_35_agent1
   + 0.08 z_3_35_agent1 + 0.08 z_2_43_agent1 + 0.08 z_3_43_agent1
   + 0.08 z_2_46_agent1 + 0.08 z_3_46_agent1 + 0.05 z_2_48_agent1
   + 0.05 z_3_48_agent1 + 0.9 z_2_54_agent1 + 0.9 z_3_54_agent1
  target_directed_route_cost: Priority=1 Weight=1 AbsTol=0 RelTol=0
   - 0.00190421133443712 x_0_11_agent0 - 0.00180121724491967 x_5_14_agent0
   - 0.00301591852968653 x_5_17_agent0 - 0.00252374830038941 x_5_21_agent0
   - 0.00378405 x_5_27_agent0 - 0.00309611240091386 x_5_35_agent0
   - 0.00260158352834534 x_5_36_agent0 - 0.00286889643243643 x_5_40_agent0
   - 0.00189084568923256 x_5_43_agent0 - 0.0036134414917725 x_5_46_agent0
   - 0.00326278985875889 x_6_17_agent0 - 0.00222420060492263 x_6_36_agent0
   - 0.00213221351733834 x_6_40_agent0 - 0.00190421133443712 x_11_0_agent0
   - 0.00160544985339413 x_11_38_agent0 - 0.00180121724491967 x_14_5_agent0
   - 0.00240109885027702 x_14_36_agent0
   - 0.00217073802410441 x_14_40_agent0 - 0.00301591852968653 x_17_5_agent0
   - 0.00326278985875889 x_17_6_agent0 - 0.00139474438781645 x_17_19_agent0
   - 0.00235549841369678 x_17_23_agent0
   - 0.00207403364997734 x_17_36_agent0
   - 0.00146000018499163 x_17_40_agent0
   - 0.00139474438781645 x_19_17_agent0
   - 0.00195452905756015 x_19_40_agent0 - 0.00252374830038941 x_21_5_agent0
   - 0.00235549841369678 x_23_17_agent0 - 0.00378405 x_27_5_agent0
   - 0.00309611240091386 x_35_5_agent0 - 0.00260158352834534 x_36_5_agent0
   - 0.00222420060492263 x_36_6_agent0 - 0.00240109885027702 x_36_14_agent0
   - 0.00207403364997734 x_36_17_agent0
   - 0.00109047940580689 x_36_38_agent0
   - 7.1545512565556412e-04 x_36_40_agent0
   - 0.00368734564760945 x_36_48_agent0
   - 0.00282022569430797 x_36_54_agent0
   - 0.00160544985339413 x_38_11_agent0
   - 0.00109047940580689 x_38_36_agent0
   - 0.00162038792744628 x_38_40_agent0 - 0.00286889643243643 x_40_5_agent0
   - 0.00213221351733834 x_40_6_agent0 - 0.00217073802410441 x_40_14_agent0
   - 0.00146000018499163 x_40_17_agent0
   - 0.00195452905756015 x_40_19_agent0
   - 7.1545512565556412e-04 x_40_36_agent0
   - 0.00162038792744628 x_40_38_agent0
   - 0.00304500846336703 x_40_48_agent0 - 0.00189084568923256 x_43_5_agent0
   - 0.0036134414917725 x_46_5_agent0 - 0.00368734564760945 x_48_36_agent0
   - 0.00304500846336703 x_48_40_agent0
   - 0.00282022569430797 x_54_36_agent0 - 0.00190421133443712 x_0_11_agent1
   - 0.00180121724491967 x_5_14_agent1 - 0.00301591852968653 x_5_17_agent1
   - 0.00252374830038941 x_5_21_agent1 - 0.00378405 x_5_27_agent1
   - 0.00309611240091386 x_5_35_agent1 - 0.00260158352834534 x_5_36_agent1
   - 0.00286889643243643 x_5_40_agent1 - 0.00189084568923256 x_5_43_agent1
   - 0.0036134414917725 x_5_46_agent1 - 0.00326278985875889 x_6_17_agent1
   - 0.00222420060492263 x_6_36_agent1 - 0.00213221351733834 x_6_40_agent1
   - 0.00190421133443712 x_11_0_agent1 - 0.00160544985339413 x_11_38_agent1
   - 0.00180121724491967 x_14_5_agent1 - 0.00240109885027702 x_14_36_agent1
   - 0.00217073802410441 x_14_40_agent1 - 0.00301591852968653 x_17_5_agent1
   - 0.00326278985875889 x_17_6_agent1 - 0.00139474438781645 x_17_19_agent1
   - 0.00235549841369678 x_17_23_agent1
   - 0.00207403364997734 x_17_36_agent1
   - 0.00146000018499163 x_17_40_agent1
   - 0.00139474438781645 x_19_17_agent1
   - 0.00195452905756015 x_19_40_agent1 - 0.00252374830038941 x_21_5_agent1
   - 0.00235549841369678 x_23_17_agent1 - 0.00378405 x_27_5_agent1
   - 0.00309611240091386 x_35_5_agent1 - 0.00260158352834534 x_36_5_agent1
   - 0.00222420060492263 x_36_6_agent1 - 0.00240109885027702 x_36_14_agent1
   - 0.00207403364997734 x_36_17_agent1
   - 0.00109047940580689 x_36_38_agent1
   - 7.1545512565556412e-04 x_36_40_agent1
   - 0.00368734564760945 x_36_48_agent1
   - 0.00282022569430797 x_36_54_agent1
   - 0.00160544985339413 x_38_11_agent1
   - 0.00109047940580689 x_38_36_agent1
   - 0.00162038792744628 x_38_40_agent1 - 0.00286889643243643 x_40_5_agent1
   - 0.00213221351733834 x_40_6_agent1 - 0.00217073802410441 x_40_14_agent1
   - 0.00146000018499163 x_40_17_agent1
   - 0.00195452905756015 x_40_19_agent1
   - 7.1545512565556412e-04 x_40_36_agent1
   - 0.00162038792744628 x_40_38_agent1
   - 0.00304500846336703 x_40_48_agent1 - 0.00189084568923256 x_43_5_agent1
   - 0.0036134414917725 x_46_5_agent1 - 0.00368734564760945 x_48_36_agent1
   - 0.00304500846336703 x_48_40_agent1
   - 0.00282022569430797 x_54_36_agent1 - 0.009375 y_5_agent0
   - 0.009375 y_11_agent0 - 0.01875 y_17_agent0 - 0.103125 y_38_agent0
   - 0.009375 y_40_agent0 - 0.006 y_53_agent0 - 0.009 y_54_agent0
   - 0.009375 y_5_agent1 - 0.009375 y_11_agent1 - 0.01875 y_17_agent1
   - 0.1125 y_36_agent1 - 0.009375 y_40_agent1 - 0.006 y_53_agent1
   - 0.009 y_54_agent1 + 0.0111809345314625 Constant1
Subject To
 depart_agent0: x_36_5_agent0 + x_36_6_agent0 + x_36_14_agent0
   + x_36_17_agent0 + x_36_38_agent0 + x_36_40_agent0 + x_36_48_agent0
   + x_36_54_agent0 = 1
 first_hop_vp_agent0: x_36_5_agent0 + x_36_6_agent0 + x_36_14_agent0
   + x_36_17_agent0 + x_36_38_agent0 + x_36_40_agent0 + x_36_48_agent0 = 1
 first_hop_grounded_vv_agent0: x_36_5_agent0 + x_36_6_agent0
   + x_36_14_agent0 + x_36_17_agent0 + x_36_38_agent0 + x_36_40_agent0
   + x_36_48_agent0 = 1
 no_return_agent0: x_5_36_agent0 + x_6_36_agent0 + x_14_36_agent0
   + x_17_36_agent0 + x_38_36_agent0 + x_40_36_agent0 + x_48_36_agent0
   + x_54_36_agent0 = 0
 flow_in_0_agent0: x_11_0_agent0 - y_0_agent0 = 0
 flow_out_0_agent0: x_0_11_agent0 - y_0_agent0 <= 0
 flow_in_5_agent0: x_14_5_agent0 + x_17_5_agent0 + x_21_5_agent0
   + x_27_5_agent0 + x_35_5_agent0 + x_36_5_agent0 + x_40_5_agent0
   + x_43_5_agent0 + x_46_5_agent0 - y_5_agent0 = 0
 flow_out_5_agent0: x_5_14_agent0 + x_5_17_agent0 + x_5_21_agent0
   + x_5_27_agent0 + x_5_35_agent0 + x_5_36_agent0 + x_5_40_agent0
   + x_5_43_agent0 + x_5_46_agent0 - y_5_agent0 <= 0
 flow_in_6_agent0: x_17_6_agent0 + x_36_6_agent0 + x_40_6_agent0
   - y_6_agent0 = 0
 flow_out_6_agent0: x_6_17_agent0 + x_6_36_agent0 + x_6_40_agent0
   - y_6_agent0 <= 0
 flow_in_11_agent0: x_0_11_agent0 + x_38_11_agent0 - y_11_agent0 = 0
 flow_out_11_agent0: x_11_0_agent0 + x_11_38_agent0 - y_11_agent0 <= 0
 flow_in_14_agent0: x_5_14_agent0 + x_36_14_agent0 + x_40_14_agent0
   - y_14_agent0 = 0
 flow_out_14_agent0: x_14_5_agent0 + x_14_36_agent0 + x_14_40_agent0
   - y_14_agent0 <= 0
 flow_in_17_agent0: x_5_17_agent0 + x_6_17_agent0 + x_19_17_agent0
   + x_23_17_agent0 + x_36_17_agent0 + x_40_17_agent0 - y_17_agent0 = 0
 flow_out_17_agent0: x_17_5_agent0 + x_17_6_agent0 + x_17_19_agent0
   + x_17_23_agent0 + x_17_36_agent0 + x_17_40_agent0 - y_17_agent0 <= 0
 flow_in_19_agent0: x_17_19_agent0 + x_40_19_agent0 - y_19_agent0 = 0
 flow_out_19_agent0: x_19_17_agent0 + x_19_40_agent0 - y_19_agent0 <= 0
 flow_in_21_agent0: x_5_21_agent0 - y_21_agent0 = 0
 flow_out_21_agent0: x_21_5_agent0 - y_21_agent0 <= 0
 flow_in_23_agent0: x_17_23_agent0 - y_23_agent0 = 0
 flow_out_23_agent0: x_23_17_agent0 - y_23_agent0 <= 0
 flow_in_27_agent0: x_5_27_agent0 - y_27_agent0 = 0
 flow_out_27_agent0: x_27_5_agent0 - y_27_agent0 <= 0
 flow_in_35_agent0: x_5_35_agent0 - y_35_agent0 = 0
 flow_out_35_agent0: x_35_5_agent0 - y_35_agent0 <= 0
 flow_in_38_agent0: x_11_38_agent0 + x_36_38_agent0 + x_40_38_agent0
   - y_38_agent0 = 0
 flow_out_38_agent0: x_38_11_agent0 + x_38_36_agent0 + x_38_40_agent0
   - y_38_agent0 <= 0
 flow_in_40_agent0: x_5_40_agent0 + x_6_40_agent0 + x_14_40_agent0
   + x_17_40_agent0 + x_19_40_agent0 + x_36_40_agent0 + x_38_40_agent0
   + x_48_40_agent0 - y_40_agent0 = 0
 flow_out_40_agent0: x_40_5_agent0 + x_40_6_agent0 + x_40_14_agent0
   + x_40_17_agent0 + x_40_19_agent0 + x_40_36_agent0 + x_40_38_agent0
   + x_40_48_agent0 - y_40_agent0 <= 0
 flow_in_43_agent0: x_5_43_agent0 - y_43_agent0 = 0
 flow_out_43_agent0: x_43_5_agent0 - y_43_agent0 <= 0
 flow_in_46_agent0: x_5_46_agent0 - y_46_agent0 = 0
 flow_out_46_agent0: x_46_5_agent0 - y_46_agent0 <= 0
 flow_in_48_agent0: x_36_48_agent0 + x_40_48_agent0 - y_48_agent0 = 0
 flow_out_48_agent0: x_48_36_agent0 + x_48_40_agent0 - y_48_agent0 <= 0
 flow_in_50_agent0: - y_50_agent0 = 0
 flow_out_50_agent0: - y_50_agent0 <= 0
 flow_in_51_agent0: - y_51_agent0 = 0
 flow_out_51_agent0: - y_51_agent0 <= 0
 flow_in_52_agent0: - y_52_agent0 = 0
 flow_out_52_agent0: - y_52_agent0 <= 0
 flow_in_53_agent0: - y_53_agent0 = 0
 flow_out_53_agent0: - y_53_agent0 <= 0
 flow_in_54_agent0: x_36_54_agent0 - y_54_agent0 = 0
 flow_out_54_agent0: x_54_36_agent0 - y_54_agent0 <= 0
 flow_in_55_agent0: - y_55_agent0 = 0
 flow_out_55_agent0: - y_55_agent0 <= 0
 flow_in_56_agent0: - y_56_agent0 = 0
 flow_out_56_agent0: - y_56_agent0 <= 0
 target_reward_visit_0_0_agent0: - y_0_agent0 + z_0_0_agent0 <= 0
 target_reward_visit_1_0_agent0: - y_0_agent0 + z_1_0_agent0 <= 0
 target_reward_visit_2_0_agent0: - y_0_agent0 + z_2_0_agent0 <= 0
 target_reward_visit_3_0_agent0: - y_0_agent0 + z_3_0_agent0 <= 0
 target_reward_visit_0_6_agent0: - y_6_agent0 + z_0_6_agent0 <= 0
 target_reward_visit_1_6_agent0: - y_6_agent0 + z_1_6_agent0 <= 0
 target_reward_visit_2_6_agent0: - y_6_agent0 + z_2_6_agent0 <= 0
 target_reward_visit_3_6_agent0: - y_6_agent0 + z_3_6_agent0 <= 0
 target_reward_visit_0_14_agent0: - y_14_agent0 + z_0_14_agent0 <= 0
 target_reward_visit_1_14_agent0: - y_14_agent0 + z_1_14_agent0 <= 0
 target_reward_visit_2_14_agent0: - y_14_agent0 + z_2_14_agent0 <= 0
 target_reward_visit_3_14_agent0: - y_14_agent0 + z_3_14_agent0 <= 0
 target_reward_visit_0_19_agent0: - y_19_agent0 + z_0_19_agent0 <= 0
 target_reward_visit_1_19_agent0: - y_19_agent0 + z_1_19_agent0 <= 0
 target_reward_visit_2_19_agent0: - y_19_agent0 + z_2_19_agent0 <= 0
 target_reward_visit_3_19_agent0: - y_19_agent0 + z_3_19_agent0 <= 0
 target_reward_visit_0_21_agent0: - y_21_agent0 + z_0_21_agent0 <= 0
 target_reward_visit_1_21_agent0: - y_21_agent0 + z_1_21_agent0 <= 0
 target_reward_visit_2_21_agent0: - y_21_agent0 + z_2_21_agent0 <= 0
 target_reward_visit_3_21_agent0: - y_21_agent0 + z_3_21_agent0 <= 0
 target_reward_visit_0_23_agent0: - y_23_agent0 + z_0_23_agent0 <= 0
 target_reward_visit_1_23_agent0: - y_23_agent0 + z_1_23_agent0 <= 0
 target_reward_visit_2_23_agent0: - y_23_agent0 + z_2_23_agent0 <= 0
 target_reward_visit_3_23_agent0: - y_23_agent0 + z_3_23_agent0 <= 0
 target_reward_visit_0_27_agent0: - y_27_agent0 + z_0_27_agent0 <= 0
 target_reward_visit_1_27_agent0: - y_27_agent0 + z_1_27_agent0 <= 0
 target_reward_visit_2_27_agent0: - y_27_agent0 + z_2_27_agent0 <= 0
 target_reward_visit_3_27_agent0: - y_27_agent0 + z_3_27_agent0 <= 0
 target_reward_visit_0_35_agent0: - y_35_agent0 + z_0_35_agent0 <= 0
 target_reward_visit_1_35_agent0: - y_35_agent0 + z_1_35_agent0 <= 0
 target_reward_visit_2_35_agent0: - y_35_agent0 + z_2_35_agent0 <= 0
 target_reward_visit_3_35_agent0: - y_35_agent0 + z_3_35_agent0 <= 0
 target_reward_visit_0_43_agent0: - y_43_agent0 + z_0_43_agent0 <= 0
 target_reward_visit_1_43_agent0: - y_43_agent0 + z_1_43_agent0 <= 0
 target_reward_visit_2_43_agent0: - y_43_agent0 + z_2_43_agent0 <= 0
 target_reward_visit_3_43_agent0: - y_43_agent0 + z_3_43_agent0 <= 0
 target_reward_visit_0_46_agent0: - y_46_agent0 + z_0_46_agent0 <= 0
 target_reward_visit_1_46_agent0: - y_46_agent0 + z_1_46_agent0 <= 0
 target_reward_visit_2_46_agent0: - y_46_agent0 + z_2_46_agent0 <= 0
 target_reward_visit_3_46_agent0: - y_46_agent0 + z_3_46_agent0 <= 0
 target_reward_visit_0_48_agent0: - y_48_agent0 + z_0_48_agent0 <= 0
 target_reward_visit_1_48_agent0: - y_48_agent0 + z_1_48_agent0 <= 0
 target_reward_visit_2_48_agent0: - y_48_agent0 + z_2_48_agent0 <= 0
 target_reward_visit_3_48_agent0: - y_48_agent0 + z_3_48_agent0 <= 0
 target_reward_visit_0_54_agent0: - y_54_agent0 + z_0_54_agent0 <= 0
 target_reward_visit_1_54_agent0: - y_54_agent0 + z_1_54_agent0 <= 0
 target_reward_visit_2_54_agent0: - y_54_agent0 + z_2_54_agent0 <= 0
 target_reward_visit_3_54_agent0: - y_54_agent0 + z_3_54_agent0 <= 0
 mtz_0_11_agent0: 24 x_0_11_agent0 + u_0_agent0 - u_11_agent0 <= 23
 mtz_5_14_agent0: 24 x_5_14_agent0 + u_5_agent0 - u_14_agent0 <= 23
 mtz_5_17_agent0: 24 x_5_17_agent0 + u_5_agent0 - u_17_agent0 <= 23
 mtz_5_21_agent0: 24 x_5_21_agent0 + u_5_agent0 - u_21_agent0 <= 23
 mtz_5_27_agent0: 24 x_5_27_agent0 + u_5_agent0 - u_27_agent0 <= 23
 mtz_5_35_agent0: 24 x_5_35_agent0 + u_5_agent0 - u_35_agent0 <= 23
 mtz_5_36_agent0: 24 x_5_36_agent0 + u_5_agent0 - u_36_agent0 <= 23
 mtz_5_40_agent0: 24 x_5_40_agent0 + u_5_agent0 - u_40_agent0 <= 23
 mtz_5_43_agent0: 24 x_5_43_agent0 + u_5_agent0 - u_43_agent0 <= 23
 mtz_5_46_agent0: 24 x_5_46_agent0 + u_5_agent0 - u_46_agent0 <= 23
 mtz_6_17_agent0: 24 x_6_17_agent0 + u_6_agent0 - u_17_agent0 <= 23
 mtz_6_36_agent0: 24 x_6_36_agent0 + u_6_agent0 - u_36_agent0 <= 23
 mtz_6_40_agent0: 24 x_6_40_agent0 + u_6_agent0 - u_40_agent0 <= 23
 mtz_11_0_agent0: 24 x_11_0_agent0 - u_0_agent0 + u_11_agent0 <= 23
 mtz_11_38_agent0: 24 x_11_38_agent0 + u_11_agent0 - u_38_agent0 <= 23
 mtz_14_5_agent0: 24 x_14_5_agent0 - u_5_agent0 + u_14_agent0 <= 23
 mtz_14_36_agent0: 24 x_14_36_agent0 + u_14_agent0 - u_36_agent0 <= 23
 mtz_14_40_agent0: 24 x_14_40_agent0 + u_14_agent0 - u_40_agent0 <= 23
 mtz_17_5_agent0: 24 x_17_5_agent0 - u_5_agent0 + u_17_agent0 <= 23
 mtz_17_6_agent0: 24 x_17_6_agent0 - u_6_agent0 + u_17_agent0 <= 23
 mtz_17_19_agent0: 24 x_17_19_agent0 + u_17_agent0 - u_19_agent0 <= 23
 mtz_17_23_agent0: 24 x_17_23_agent0 + u_17_agent0 - u_23_agent0 <= 23
 mtz_17_36_agent0: 24 x_17_36_agent0 + u_17_agent0 - u_36_agent0 <= 23
 mtz_17_40_agent0: 24 x_17_40_agent0 + u_17_agent0 - u_40_agent0 <= 23
 mtz_19_17_agent0: 24 x_19_17_agent0 - u_17_agent0 + u_19_agent0 <= 23
 mtz_19_40_agent0: 24 x_19_40_agent0 + u_19_agent0 - u_40_agent0 <= 23
 mtz_21_5_agent0: 24 x_21_5_agent0 - u_5_agent0 + u_21_agent0 <= 23
 mtz_23_17_agent0: 24 x_23_17_agent0 - u_17_agent0 + u_23_agent0 <= 23
 mtz_27_5_agent0: 24 x_27_5_agent0 - u_5_agent0 + u_27_agent0 <= 23
 mtz_35_5_agent0: 24 x_35_5_agent0 - u_5_agent0 + u_35_agent0 <= 23
 mtz_36_5_agent0: 24 x_36_5_agent0 - u_5_agent0 + u_36_agent0 <= 23
 mtz_36_6_agent0: 24 x_36_6_agent0 - u_6_agent0 + u_36_agent0 <= 23
 mtz_36_14_agent0: 24 x_36_14_agent0 - u_14_agent0 + u_36_agent0 <= 23
 mtz_36_17_agent0: 24 x_36_17_agent0 - u_17_agent0 + u_36_agent0 <= 23
 mtz_36_38_agent0: 24 x_36_38_agent0 + u_36_agent0 - u_38_agent0 <= 23
 mtz_36_40_agent0: 24 x_36_40_agent0 + u_36_agent0 - u_40_agent0 <= 23
 mtz_36_48_agent0: 24 x_36_48_agent0 + u_36_agent0 - u_48_agent0 <= 23
 mtz_36_54_agent0: 24 x_36_54_agent0 + u_36_agent0 - u_54_agent0 <= 23
 mtz_38_11_agent0: 24 x_38_11_agent0 - u_11_agent0 + u_38_agent0 <= 23
 mtz_38_36_agent0: 24 x_38_36_agent0 - u_36_agent0 + u_38_agent0 <= 23
 mtz_38_40_agent0: 24 x_38_40_agent0 + u_38_agent0 - u_40_agent0 <= 23
 mtz_40_5_agent0: 24 x_40_5_agent0 - u_5_agent0 + u_40_agent0 <= 23
 mtz_40_6_agent0: 24 x_40_6_agent0 - u_6_agent0 + u_40_agent0 <= 23
 mtz_40_14_agent0: 24 x_40_14_agent0 - u_14_agent0 + u_40_agent0 <= 23
 mtz_40_17_agent0: 24 x_40_17_agent0 - u_17_agent0 + u_40_agent0 <= 23
 mtz_40_19_agent0: 24 x_40_19_agent0 - u_19_agent0 + u_40_agent0 <= 23
 mtz_40_36_agent0: 24 x_40_36_agent0 - u_36_agent0 + u_40_agent0 <= 23
 mtz_40_38_agent0: 24 x_40_38_agent0 - u_38_agent0 + u_40_agent0 <= 23
 mtz_40_48_agent0: 24 x_40_48_agent0 + u_40_agent0 - u_48_agent0 <= 23
 mtz_43_5_agent0: 24 x_43_5_agent0 - u_5_agent0 + u_43_agent0 <= 23
 mtz_46_5_agent0: 24 x_46_5_agent0 - u_5_agent0 + u_46_agent0 <= 23
 mtz_48_36_agent0: 24 x_48_36_agent0 - u_36_agent0 + u_48_agent0 <= 23
 mtz_48_40_agent0: 24 x_48_40_agent0 - u_40_agent0 + u_48_agent0 <= 23
 mtz_54_36_agent0: 24 x_54_36_agent0 - u_36_agent0 + u_54_agent0 <= 23
 depart_agent1: x_38_11_agent1 + x_38_36_agent1 + x_38_40_agent1 = 1
 first_hop_vp_agent1: x_38_11_agent1 + x_38_36_agent1 + x_38_40_agent1 = 1
 first_hop_grounded_vv_agent1: x_38_11_agent1 + x_38_36_agent1
   + x_38_40_agent1 = 1
 no_return_agent1: x_11_38_agent1 + x_36_38_agent1 + x_40_38_agent1 = 0
 flow_in_0_agent1: x_11_0_agent1 - y_0_agent1 = 0
 flow_out_0_agent1: x_0_11_agent1 - y_0_agent1 <= 0
 flow_in_5_agent1: x_14_5_agent1 + x_17_5_agent1 + x_21_5_agent1
   + x_27_5_agent1 + x_35_5_agent1 + x_36_5_agent1 + x_40_5_agent1
   + x_43_5_agent1 + x_46_5_agent1 - y_5_agent1 = 0
 flow_out_5_agent1: x_5_14_agent1 + x_5_17_agent1 + x_5_21_agent1
   + x_5_27_agent1 + x_5_35_agent1 + x_5_36_agent1 + x_5_40_agent1
   + x_5_43_agent1 + x_5_46_agent1 - y_5_agent1 <= 0
 flow_in_6_agent1: x_17_6_agent1 + x_36_6_agent1 + x_40_6_agent1
   - y_6_agent1 = 0
 flow_out_6_agent1: x_6_17_agent1 + x_6_36_agent1 + x_6_40_agent1
   - y_6_agent1 <= 0
 flow_in_11_agent1: x_0_11_agent1 + x_38_11_agent1 - y_11_agent1 = 0
 flow_out_11_agent1: x_11_0_agent1 + x_11_38_agent1 - y_11_agent1 <= 0
 flow_in_14_agent1: x_5_14_agent1 + x_36_14_agent1 + x_40_14_agent1
   - y_14_agent1 = 0
 flow_out_14_agent1: x_14_5_agent1 + x_14_36_agent1 + x_14_40_agent1
   - y_14_agent1 <= 0
 flow_in_17_agent1: x_5_17_agent1 + x_6_17_agent1 + x_19_17_agent1
   + x_23_17_agent1 + x_36_17_agent1 + x_40_17_agent1 - y_17_agent1 = 0
 flow_out_17_agent1: x_17_5_agent1 + x_17_6_agent1 + x_17_19_agent1
   + x_17_23_agent1 + x_17_36_agent1 + x_17_40_agent1 - y_17_agent1 <= 0
 flow_in_19_agent1: x_17_19_agent1 + x_40_19_agent1 - y_19_agent1 = 0
 flow_out_19_agent1: x_19_17_agent1 + x_19_40_agent1 - y_19_agent1 <= 0
 flow_in_21_agent1: x_5_21_agent1 - y_21_agent1 = 0
 flow_out_21_agent1: x_21_5_agent1 - y_21_agent1 <= 0
 flow_in_23_agent1: x_17_23_agent1 - y_23_agent1 = 0
 flow_out_23_agent1: x_23_17_agent1 - y_23_agent1 <= 0
 flow_in_27_agent1: x_5_27_agent1 - y_27_agent1 = 0
 flow_out_27_agent1: x_27_5_agent1 - y_27_agent1 <= 0
 flow_in_35_agent1: x_5_35_agent1 - y_35_agent1 = 0
 flow_out_35_agent1: x_35_5_agent1 - y_35_agent1 <= 0
 flow_in_36_agent1: x_5_36_agent1 + x_6_36_agent1 + x_14_36_agent1
   + x_17_36_agent1 + x_38_36_agent1 + x_40_36_agent1 + x_48_36_agent1
   + x_54_36_agent1 - y_36_agent1 = 0
 flow_out_36_agent1: x_36_5_agent1 + x_36_6_agent1 + x_36_14_agent1
   + x_36_17_agent1 + x_36_38_agent1 + x_36_40_agent1 + x_36_48_agent1
   + x_36_54_agent1 - y_36_agent1 <= 0
 flow_in_40_agent1: x_5_40_agent1 + x_6_40_agent1 + x_14_40_agent1
   + x_17_40_agent1 + x_19_40_agent1 + x_36_40_agent1 + x_38_40_agent1
   + x_48_40_agent1 - y_40_agent1 = 0
 flow_out_40_agent1: x_40_5_agent1 + x_40_6_agent1 + x_40_14_agent1
   + x_40_17_agent1 + x_40_19_agent1 + x_40_36_agent1 + x_40_38_agent1
   + x_40_48_agent1 - y_40_agent1 <= 0
 flow_in_43_agent1: x_5_43_agent1 - y_43_agent1 = 0
 flow_out_43_agent1: x_43_5_agent1 - y_43_agent1 <= 0
 flow_in_46_agent1: x_5_46_agent1 - y_46_agent1 = 0
 flow_out_46_agent1: x_46_5_agent1 - y_46_agent1 <= 0
 flow_in_48_agent1: x_36_48_agent1 + x_40_48_agent1 - y_48_agent1 = 0
 flow_out_48_agent1: x_48_36_agent1 + x_48_40_agent1 - y_48_agent1 <= 0
 flow_in_50_agent1: - y_50_agent1 = 0
 flow_out_50_agent1: - y_50_agent1 <= 0
 flow_in_51_agent1: - y_51_agent1 = 0
 flow_out_51_agent1: - y_51_agent1 <= 0
 flow_in_52_agent1: - y_52_agent1 = 0
 flow_out_52_agent1: - y_52_agent1 <= 0
 flow_in_53_agent1: - y_53_agent1 = 0
 flow_out_53_agent1: - y_53_agent1 <= 0
 flow_in_54_agent1: x_36_54_agent1 - y_54_agent1 = 0
 flow_out_54_agent1: x_54_36_agent1 - y_54_agent1 <= 0
 flow_in_55_agent1: - y_55_agent1 = 0
 flow_out_55_agent1: - y_55_agent1 <= 0
 flow_in_56_agent1: - y_56_agent1 = 0
 flow_out_56_agent1: - y_56_agent1 <= 0
 target_reward_visit_0_0_agent1: - y_0_agent1 + z_0_0_agent1 <= 0
 target_reward_visit_1_0_agent1: - y_0_agent1 + z_1_0_agent1 <= 0
 target_reward_visit_2_0_agent1: - y_0_agent1 + z_2_0_agent1 <= 0
 target_reward_visit_3_0_agent1: - y_0_agent1 + z_3_0_agent1 <= 0
 target_reward_visit_0_6_agent1: - y_6_agent1 + z_0_6_agent1 <= 0
 target_reward_visit_1_6_agent1: - y_6_agent1 + z_1_6_agent1 <= 0
 target_reward_visit_2_6_agent1: - y_6_agent1 + z_2_6_agent1 <= 0
 target_reward_visit_3_6_agent1: - y_6_agent1 + z_3_6_agent1 <= 0
 target_reward_visit_0_14_agent1: - y_14_agent1 + z_0_14_agent1 <= 0
 target_reward_visit_1_14_agent1: - y_14_agent1 + z_1_14_agent1 <= 0
 target_reward_visit_2_14_agent1: - y_14_agent1 + z_2_14_agent1 <= 0
 target_reward_visit_3_14_agent1: - y_14_agent1 + z_3_14_agent1 <= 0
 target_reward_visit_0_19_agent1: - y_19_agent1 + z_0_19_agent1 <= 0
 target_reward_visit_1_19_agent1: - y_19_agent1 + z_1_19_agent1 <= 0
 target_reward_visit_2_19_agent1: - y_19_agent1 + z_2_19_agent1 <= 0
 target_reward_visit_3_19_agent1: - y_19_agent1 + z_3_19_agent1 <= 0
 target_reward_visit_0_21_agent1: - y_21_agent1 + z_0_21_agent1 <= 0
 target_reward_visit_1_21_agent1: - y_21_agent1 + z_1_21_agent1 <= 0
 target_reward_visit_2_21_agent1: - y_21_agent1 + z_2_21_agent1 <= 0
 target_reward_visit_3_21_agent1: - y_21_agent1 + z_3_21_agent1 <= 0
 target_reward_visit_0_23_agent1: - y_23_agent1 + z_0_23_agent1 <= 0
 target_reward_visit_1_23_agent1: - y_23_agent1 + z_1_23_agent1 <= 0
 target_reward_visit_2_23_agent1: - y_23_agent1 + z_2_23_agent1 <= 0
 target_reward_visit_3_23_agent1: - y_23_agent1 + z_3_23_agent1 <= 0
 target_reward_visit_0_27_agent1: - y_27_agent1 + z_0_27_agent1 <= 0
 target_reward_visit_1_27_agent1: - y_27_agent1 + z_1_27_agent1 <= 0
 target_reward_visit_2_27_agent1: - y_27_agent1 + z_2_27_agent1 <= 0
 target_reward_visit_3_27_agent1: - y_27_agent1 + z_3_27_agent1 <= 0
 target_reward_visit_0_35_agent1: - y_35_agent1 + z_0_35_agent1 <= 0
 target_reward_visit_1_35_agent1: - y_35_agent1 + z_1_35_agent1 <= 0
 target_reward_visit_2_35_agent1: - y_35_agent1 + z_2_35_agent1 <= 0
 target_reward_visit_3_35_agent1: - y_35_agent1 + z_3_35_agent1 <= 0
 target_reward_visit_0_43_agent1: - y_43_agent1 + z_0_43_agent1 <= 0
 target_reward_visit_1_43_agent1: - y_43_agent1 + z_1_43_agent1 <= 0
 target_reward_visit_2_43_agent1: - y_43_agent1 + z_2_43_agent1 <= 0
 target_reward_visit_3_43_agent1: - y_43_agent1 + z_3_43_agent1 <= 0
 target_reward_visit_0_46_agent1: - y_46_agent1 + z_0_46_agent1 <= 0
 target_reward_visit_1_46_agent1: - y_46_agent1 + z_1_46_agent1 <= 0
 target_reward_visit_2_46_agent1: - y_46_agent1 + z_2_46_agent1 <= 0
 target_reward_visit_3_46_agent1: - y_46_agent1 + z_3_46_agent1 <= 0
 target_reward_visit_0_48_agent1: - y_48_agent1 + z_0_48_agent1 <= 0
 target_reward_visit_1_48_agent1: - y_48_agent1 + z_1_48_agent1 <= 0
 target_reward_visit_2_48_agent1: - y_48_agent1 + z_2_48_agent1 <= 0
 target_reward_visit_3_48_agent1: - y_48_agent1 + z_3_48_agent1 <= 0
 target_reward_visit_0_54_agent1: - y_54_agent1 + z_0_54_agent1 <= 0
 target_reward_visit_1_54_agent1: - y_54_agent1 + z_1_54_agent1 <= 0
 target_reward_visit_2_54_agent1: - y_54_agent1 + z_2_54_agent1 <= 0
 target_reward_visit_3_54_agent1: - y_54_agent1 + z_3_54_agent1 <= 0
 mtz_0_11_agent1: 24 x_0_11_agent1 + u_0_agent1 - u_11_agent1 <= 23
 mtz_5_14_agent1: 24 x_5_14_agent1 + u_5_agent1 - u_14_agent1 <= 23
 mtz_5_17_agent1: 24 x_5_17_agent1 + u_5_agent1 - u_17_agent1 <= 23
 mtz_5_21_agent1: 24 x_5_21_agent1 + u_5_agent1 - u_21_agent1 <= 23
 mtz_5_27_agent1: 24 x_5_27_agent1 + u_5_agent1 - u_27_agent1 <= 23
 mtz_5_35_agent1: 24 x_5_35_agent1 + u_5_agent1 - u_35_agent1 <= 23
 mtz_5_36_agent1: 24 x_5_36_agent1 + u_5_agent1 - u_36_agent1 <= 23
 mtz_5_40_agent1: 24 x_5_40_agent1 + u_5_agent1 - u_40_agent1 <= 23
 mtz_5_43_agent1: 24 x_5_43_agent1 + u_5_agent1 - u_43_agent1 <= 23
 mtz_5_46_agent1: 24 x_5_46_agent1 + u_5_agent1 - u_46_agent1 <= 23
 mtz_6_17_agent1: 24 x_6_17_agent1 + u_6_agent1 - u_17_agent1 <= 23
 mtz_6_36_agent1: 24 x_6_36_agent1 + u_6_agent1 - u_36_agent1 <= 23
 mtz_6_40_agent1: 24 x_6_40_agent1 + u_6_agent1 - u_40_agent1 <= 23
 mtz_11_0_agent1: 24 x_11_0_agent1 - u_0_agent1 + u_11_agent1 <= 23
 mtz_11_38_agent1: 24 x_11_38_agent1 + u_11_agent1 - u_38_agent1 <= 23
 mtz_14_5_agent1: 24 x_14_5_agent1 - u_5_agent1 + u_14_agent1 <= 23
 mtz_14_36_agent1: 24 x_14_36_agent1 + u_14_agent1 - u_36_agent1 <= 23
 mtz_14_40_agent1: 24 x_14_40_agent1 + u_14_agent1 - u_40_agent1 <= 23
 mtz_17_5_agent1: 24 x_17_5_agent1 - u_5_agent1 + u_17_agent1 <= 23
 mtz_17_6_agent1: 24 x_17_6_agent1 - u_6_agent1 + u_17_agent1 <= 23
 mtz_17_19_agent1: 24 x_17_19_agent1 + u_17_agent1 - u_19_agent1 <= 23
 mtz_17_23_agent1: 24 x_17_23_agent1 + u_17_agent1 - u_23_agent1 <= 23
 mtz_17_36_agent1: 24 x_17_36_agent1 + u_17_agent1 - u_36_agent1 <= 23
 mtz_17_40_agent1: 24 x_17_40_agent1 + u_17_agent1 - u_40_agent1 <= 23
 mtz_19_17_agent1: 24 x_19_17_agent1 - u_17_agent1 + u_19_agent1 <= 23
 mtz_19_40_agent1: 24 x_19_40_agent1 + u_19_agent1 - u_40_agent1 <= 23
 mtz_21_5_agent1: 24 x_21_5_agent1 - u_5_agent1 + u_21_agent1 <= 23
 mtz_23_17_agent1: 24 x_23_17_agent1 - u_17_agent1 + u_23_agent1 <= 23
 mtz_27_5_agent1: 24 x_27_5_agent1 - u_5_agent1 + u_27_agent1 <= 23
 mtz_35_5_agent1: 24 x_35_5_agent1 - u_5_agent1 + u_35_agent1 <= 23
 mtz_36_5_agent1: 24 x_36_5_agent1 - u_5_agent1 + u_36_agent1 <= 23
 mtz_36_6_agent1: 24 x_36_6_agent1 - u_6_agent1 + u_36_agent1 <= 23
 mtz_36_14_agent1: 24 x_36_14_agent1 - u_14_agent1 + u_36_agent1 <= 23
 mtz_36_17_agent1: 24 x_36_17_agent1 - u_17_agent1 + u_36_agent1 <= 23
 mtz_36_38_agent1: 24 x_36_38_agent1 + u_36_agent1 - u_38_agent1 <= 23
 mtz_36_40_agent1: 24 x_36_40_agent1 + u_36_agent1 - u_40_agent1 <= 23
 mtz_36_48_agent1: 24 x_36_48_agent1 + u_36_agent1 - u_48_agent1 <= 23
 mtz_36_54_agent1: 24 x_36_54_agent1 + u_36_agent1 - u_54_agent1 <= 23
 mtz_38_11_agent1: 24 x_38_11_agent1 - u_11_agent1 + u_38_agent1 <= 23
 mtz_38_36_agent1: 24 x_38_36_agent1 - u_36_agent1 + u_38_agent1 <= 23
 mtz_38_40_agent1: 24 x_38_40_agent1 + u_38_agent1 - u_40_agent1 <= 23
 mtz_40_5_agent1: 24 x_40_5_agent1 - u_5_agent1 + u_40_agent1 <= 23
 mtz_40_6_agent1: 24 x_40_6_agent1 - u_6_agent1 + u_40_agent1 <= 23
 mtz_40_14_agent1: 24 x_40_14_agent1 - u_14_agent1 + u_40_agent1 <= 23
 mtz_40_17_agent1: 24 x_40_17_agent1 - u_17_agent1 + u_40_agent1 <= 23
 mtz_40_19_agent1: 24 x_40_19_agent1 - u_19_agent1 + u_40_agent1 <= 23
 mtz_40_36_agent1: 24 x_40_36_agent1 - u_36_agent1 + u_40_agent1 <= 23
 mtz_40_38_agent1: 24 x_40_38_agent1 - u_38_agent1 + u_40_agent1 <= 23
 mtz_40_48_agent1: 24 x_40_48_agent1 + u_40_agent1 - u_48_agent1 <= 23
 mtz_43_5_agent1: 24 x_43_5_agent1 - u_5_agent1 + u_43_agent1 <= 23
 mtz_46_5_agent1: 24 x_46_5_agent1 - u_5_agent1 + u_46_agent1 <= 23
 mtz_48_36_agent1: 24 x_48_36_agent1 - u_36_agent1 + u_48_agent1 <= 23
 mtz_48_40_agent1: 24 x_48_40_agent1 - u_40_agent1 + u_48_agent1 <= 23
 mtz_54_36_agent1: 24 x_54_36_agent1 - u_36_agent1 + u_54_agent1 <= 23
 target_reward_positive_0_0_agent0: z_0_0_agent0 = 0
 target_reward_positive_0_6_agent0: z_0_6_agent0 = 0
 target_reward_positive_0_14_agent0: z_0_14_agent0 = 0
 target_reward_positive_0_19_agent0: z_0_19_agent0 = 0
 target_reward_positive_0_21_agent0: z_0_21_agent0 = 0
 target_reward_positive_0_23_agent0: z_0_23_agent0 = 0
 target_reward_positive_0_27_agent0: z_0_27_agent0 = 0
 target_reward_positive_0_35_agent0: z_0_35_agent0 = 0
 target_reward_positive_0_43_agent0: z_0_43_agent0 = 0
 target_reward_positive_0_46_agent0: z_0_46_agent0 = 0
 target_reward_positive_0_48_agent0: z_0_48_agent0 = 0
 target_reward_positive_0_54_agent0: z_0_54_agent0 = 0
 target_reward_positive_0_0_agent1: z_0_0_agent1 = 0
 target_reward_positive_0_6_agent1: z_0_6_agent1 = 0
 target_reward_positive_0_14_agent1: z_0_14_agent1 = 0
 target_reward_positive_0_19_agent1: z_0_19_agent1 = 0
 target_reward_positive_0_21_agent1: z_0_21_agent1 = 0
 target_reward_positive_0_23_agent1: z_0_23_agent1 = 0
 target_reward_positive_0_27_agent1: z_0_27_agent1 = 0
 target_reward_positive_0_35_agent1: z_0_35_agent1 = 0
 target_reward_positive_0_43_agent1: z_0_43_agent1 = 0
 target_reward_positive_0_46_agent1: z_0_46_agent1 = 0
 target_reward_positive_0_48_agent1: z_0_48_agent1 = 0
 target_reward_positive_0_54_agent1: z_0_54_agent1 = 0
 target_reward_positive_1_0_agent0: z_1_0_agent0 = 0
 target_reward_positive_1_6_agent0: z_1_6_agent0 = 0
 target_reward_positive_1_14_agent0: z_1_14_agent0 = 0
 target_reward_positive_1_19_agent0: z_1_19_agent0 = 0
 target_reward_positive_1_21_agent0: z_1_21_agent0 = 0
 target_reward_positive_1_23_agent0: z_1_23_agent0 = 0
 target_reward_positive_1_27_agent0: z_1_27_agent0 = 0
 target_reward_positive_1_35_agent0: z_1_35_agent0 = 0
 target_reward_positive_1_43_agent0: z_1_43_agent0 = 0
 target_reward_positive_1_46_agent0: z_1_46_agent0 = 0
 target_reward_positive_1_48_agent0: z_1_48_agent0 = 0
 target_reward_positive_1_54_agent0: z_1_54_agent0 = 0
 target_reward_positive_1_0_agent1: z_1_0_agent1 = 0
 target_reward_positive_1_6_agent1: z_1_6_agent1 = 0
 target_reward_positive_1_14_agent1: z_1_14_agent1 = 0
 target_reward_positive_1_19_agent1: z_1_19_agent1 = 0
 target_reward_positive_1_21_agent1: z_1_21_agent1 = 0
 target_reward_positive_1_23_agent1: z_1_23_agent1 = 0
 target_reward_positive_1_27_agent1: z_1_27_agent1 = 0
 target_reward_positive_1_35_agent1: z_1_35_agent1 = 0
 target_reward_positive_1_43_agent1: z_1_43_agent1 = 0
 target_reward_positive_1_46_agent1: z_1_46_agent1 = 0
 target_reward_positive_1_48_agent1: z_1_48_agent1 = 0
 target_reward_positive_1_54_agent1: z_1_54_agent1 = 0
 target_reward_found_0: z_0_0_agent0 + z_0_6_agent0 + z_0_14_agent0
   + z_0_19_agent0 + z_0_21_agent0 + z_0_23_agent0 + z_0_27_agent0
   + z_0_35_agent0 + z_0_43_agent0 + z_0_46_agent0 + z_0_48_agent0
   + z_0_54_agent0 + z_0_0_agent1 + z_0_6_agent1 + z_0_14_agent1
   + z_0_19_agent1 + z_0_21_agent1 + z_0_23_agent1 + z_0_27_agent1
   + z_0_35_agent1 + z_0_43_agent1 + z_0_46_agent1 + z_0_48_agent1
   + z_0_54_agent1 = 0
 target_reward_found_1: z_1_0_agent0 + z_1_6_agent0 + z_1_14_agent0
   + z_1_19_agent0 + z_1_21_agent0 + z_1_23_agent0 + z_1_27_agent0
   + z_1_35_agent0 + z_1_43_agent0 + z_1_46_agent0 + z_1_48_agent0
   + z_1_54_agent0 + z_1_0_agent1 + z_1_6_agent1 + z_1_14_agent1
   + z_1_19_agent1 + z_1_21_agent1 + z_1_23_agent1 + z_1_27_agent1
   + z_1_35_agent1 + z_1_43_agent1 + z_1_46_agent1 + z_1_48_agent1
   + z_1_54_agent1 = 0
 target_reward_unique_2: z_2_0_agent0 + z_2_6_agent0 + z_2_14_agent0
   + z_2_19_agent0 + z_2_21_agent0 + z_2_23_agent0 + z_2_27_agent0
   + z_2_35_agent0 + z_2_43_agent0 + z_2_46_agent0 + z_2_48_agent0
   + z_2_54_agent0 + z_2_0_agent1 + z_2_6_agent1 + z_2_14_agent1
   + z_2_19_agent1 + z_2_21_agent1 + z_2_23_agent1 + z_2_27_agent1
   + z_2_35_agent1 + z_2_43_agent1 + z_2_46_agent1 + z_2_48_agent1
   + z_2_54_agent1 = 1
 target_reward_unique_3: z_3_0_agent0 + z_3_6_agent0 + z_3_14_agent0
   + z_3_19_agent0 + z_3_21_agent0 + z_3_23_agent0 + z_3_27_agent0
   + z_3_35_agent0 + z_3_43_agent0 + z_3_46_agent0 + z_3_48_agent0
   + z_3_54_agent0 + z_3_0_agent1 + z_3_6_agent1 + z_3_14_agent1
   + z_3_19_agent1 + z_3_21_agent1 + z_3_23_agent1 + z_3_27_agent1
   + z_3_35_agent1 + z_3_43_agent1 + z_3_46_agent1 + z_3_48_agent1
   + z_3_54_agent1 = 1
 target_directed_agent_assignment_agent0: z_2_0_agent0 + z_3_0_agent0
   + z_2_6_agent0 + z_3_6_agent0 + z_2_14_agent0 + z_3_14_agent0
   + z_2_19_agent0 + z_3_19_agent0 + z_2_21_agent0 + z_3_21_agent0
   + z_2_23_agent0 + z_3_23_agent0 + z_2_27_agent0 + z_3_27_agent0
   + z_2_35_agent0 + z_3_35_agent0 + z_2_43_agent0 + z_3_43_agent0
   + z_2_46_agent0 + z_3_46_agent0 + z_2_48_agent0 + z_3_48_agent0
   + z_2_54_agent0 + z_3_54_agent0 >= 1
 target_directed_agent_assignment_agent1: z_2_0_agent1 + z_3_0_agent1
   + z_2_6_agent1 + z_3_6_agent1 + z_2_14_agent1 + z_3_14_agent1
   + z_2_19_agent1 + z_3_19_agent1 + z_2_21_agent1 + z_3_21_agent1
   + z_2_23_agent1 + z_3_23_agent1 + z_2_27_agent1 + z_3_27_agent1
   + z_2_35_agent1 + z_3_35_agent1 + z_2_43_agent1 + z_3_43_agent1
   + z_2_46_agent1 + z_3_46_agent1 + z_2_48_agent1 + z_3_48_agent1
   + z_2_54_agent1 + z_3_54_agent1 >= 1
 unique_action_agent0_agent1_0: <= 1
 unique_action_agent0_agent1_5: x_36_5_agent0 <= 1
 unique_action_agent0_agent1_6: x_36_6_agent0 <= 1
 unique_action_agent0_agent1_11: x_38_11_agent1 <= 1
 unique_action_agent0_agent1_14: x_36_14_agent0 <= 1
 unique_action_agent0_agent1_17: x_36_17_agent0 <= 1
 unique_action_agent0_agent1_19: <= 1
 unique_action_agent0_agent1_21: <= 1
 unique_action_agent0_agent1_23: <= 1
 unique_action_agent0_agent1_27: <= 1
 unique_action_agent0_agent1_35: <= 1
 unique_action_agent0_agent1_36: x_38_36_agent1 <= 1
 unique_action_agent0_agent1_38: x_36_38_agent0 <= 1
 unique_action_agent0_agent1_40: x_36_40_agent0 + x_38_40_agent1 <= 1
 unique_action_agent0_agent1_43: <= 1
 unique_action_agent0_agent1_46: <= 1
 unique_action_agent0_agent1_48: x_36_48_agent0 <= 1
Bounds
 1 <= u_0_agent0 <= 24
 1 <= u_5_agent0 <= 24
 1 <= u_6_agent0 <= 24
 1 <= u_11_agent0 <= 24
 1 <= u_14_agent0 <= 24
 1 <= u_17_agent0 <= 24
 1 <= u_19_agent0 <= 24
 1 <= u_21_agent0 <= 24
 1 <= u_23_agent0 <= 24
 1 <= u_27_agent0 <= 24
 1 <= u_35_agent0 <= 24
 1 <= u_36_agent0 <= 24
 1 <= u_38_agent0 <= 24
 1 <= u_40_agent0 <= 24
 1 <= u_43_agent0 <= 24
 1 <= u_46_agent0 <= 24
 1 <= u_48_agent0 <= 24
 1 <= u_50_agent0 <= 24
 1 <= u_51_agent0 <= 24
 1 <= u_52_agent0 <= 24
 1 <= u_53_agent0 <= 24
 1 <= u_54_agent0 <= 24
 1 <= u_55_agent0 <= 24
 1 <= u_56_agent0 <= 24
 1 <= u_0_agent1 <= 24
 1 <= u_5_agent1 <= 24
 1 <= u_6_agent1 <= 24
 1 <= u_11_agent1 <= 24
 1 <= u_14_agent1 <= 24
 1 <= u_17_agent1 <= 24
 1 <= u_19_agent1 <= 24
 1 <= u_21_agent1 <= 24
 1 <= u_23_agent1 <= 24
 1 <= u_27_agent1 <= 24
 1 <= u_35_agent1 <= 24
 1 <= u_36_agent1 <= 24
 1 <= u_38_agent1 <= 24
 1 <= u_40_agent1 <= 24
 1 <= u_43_agent1 <= 24
 1 <= u_46_agent1 <= 24
 1 <= u_48_agent1 <= 24
 1 <= u_50_agent1 <= 24
 1 <= u_51_agent1 <= 24
 1 <= u_52_agent1 <= 24
 1 <= u_53_agent1 <= 24
 1 <= u_54_agent1 <= 24
 1 <= u_55_agent1 <= 24
 1 <= u_56_agent1 <= 24
 Constant1 = 1
Binaries
 x_0_11_agent0 x_5_14_agent0 x_5_17_agent0 x_5_21_agent0 x_5_27_agent0
 x_5_35_agent0 x_5_36_agent0 x_5_40_agent0 x_5_43_agent0 x_5_46_agent0
 x_6_17_agent0 x_6_36_agent0 x_6_40_agent0 x_11_0_agent0 x_11_38_agent0
 x_14_5_agent0 x_14_36_agent0 x_14_40_agent0 x_17_5_agent0 x_17_6_agent0
 x_17_19_agent0 x_17_23_agent0 x_17_36_agent0 x_17_40_agent0 x_19_17_agent0
 x_19_40_agent0 x_21_5_agent0 x_23_17_agent0 x_27_5_agent0 x_35_5_agent0
 x_36_5_agent0 x_36_6_agent0 x_36_14_agent0 x_36_17_agent0 x_36_38_agent0
 x_36_40_agent0 x_36_48_agent0 x_36_54_agent0 x_38_11_agent0 x_38_36_agent0
 x_38_40_agent0 x_40_5_agent0 x_40_6_agent0 x_40_14_agent0 x_40_17_agent0
 x_40_19_agent0 x_40_36_agent0 x_40_38_agent0 x_40_48_agent0 x_43_5_agent0
 x_46_5_agent0 x_48_36_agent0 x_48_40_agent0 x_54_36_agent0 x_0_11_agent1
 x_5_14_agent1 x_5_17_agent1 x_5_21_agent1 x_5_27_agent1 x_5_35_agent1
 x_5_36_agent1 x_5_40_agent1 x_5_43_agent1 x_5_46_agent1 x_6_17_agent1
 x_6_36_agent1 x_6_40_agent1 x_11_0_agent1 x_11_38_agent1 x_14_5_agent1
 x_14_36_agent1 x_14_40_agent1 x_17_5_agent1 x_17_6_agent1 x_17_19_agent1
 x_17_23_agent1 x_17_36_agent1 x_17_40_agent1 x_19_17_agent1 x_19_40_agent1
 x_21_5_agent1 x_23_17_agent1 x_27_5_agent1 x_35_5_agent1 x_36_5_agent1
 x_36_6_agent1 x_36_14_agent1 x_36_17_agent1 x_36_38_agent1 x_36_40_agent1
 x_36_48_agent1 x_36_54_agent1 x_38_11_agent1 x_38_36_agent1 x_38_40_agent1
 x_40_5_agent1 x_40_6_agent1 x_40_14_agent1 x_40_17_agent1 x_40_19_agent1
 x_40_36_agent1 x_40_38_agent1 x_40_48_agent1 x_43_5_agent1 x_46_5_agent1
 x_48_36_agent1 x_48_40_agent1 x_54_36_agent1 y_0_agent0 y_5_agent0
 y_6_agent0 y_11_agent0 y_14_agent0 y_17_agent0 y_19_agent0 y_21_agent0
 y_23_agent0 y_27_agent0 y_35_agent0 y_38_agent0 y_40_agent0 y_43_agent0
 y_46_agent0 y_48_agent0 y_50_agent0 y_51_agent0 y_52_agent0 y_53_agent0
 y_54_agent0 y_55_agent0 y_56_agent0 y_0_agent1 y_5_agent1 y_6_agent1
 y_11_agent1 y_14_agent1 y_17_agent1 y_19_agent1 y_21_agent1 y_23_agent1
 y_27_agent1 y_35_agent1 y_36_agent1 y_40_agent1 y_43_agent1 y_46_agent1
 y_48_agent1 y_50_agent1 y_51_agent1 y_52_agent1 y_53_agent1 y_54_agent1
 y_55_agent1 y_56_agent1 z_0_0_agent0 z_1_0_agent0 z_2_0_agent0
 z_3_0_agent0 z_0_6_agent0 z_1_6_agent0 z_2_6_agent0 z_3_6_agent0
 z_0_14_agent0 z_1_14_agent0 z_2_14_agent0 z_3_14_agent0 z_0_19_agent0
 z_1_19_agent0 z_2_19_agent0 z_3_19_agent0 z_0_21_agent0 z_1_21_agent0
 z_2_21_agent0 z_3_21_agent0 z_0_23_agent0 z_1_23_agent0 z_2_23_agent0
 z_3_23_agent0 z_0_27_agent0 z_1_27_agent0 z_2_27_agent0 z_3_27_agent0
 z_0_35_agent0 z_1_35_agent0 z_2_35_agent0 z_3_35_agent0 z_0_43_agent0
 z_1_43_agent0 z_2_43_agent0 z_3_43_agent0 z_0_46_agent0 z_1_46_agent0
 z_2_46_agent0 z_3_46_agent0 z_0_48_agent0 z_1_48_agent0 z_2_48_agent0
 z_3_48_agent0 z_0_54_agent0 z_1_54_agent0 z_2_54_agent0 z_3_54_agent0
 z_0_0_agent1 z_1_0_agent1 z_2_0_agent1 z_3_0_agent1 z_0_6_agent1
 z_1_6_agent1 z_2_6_agent1 z_3_6_agent1 z_0_14_agent1 z_1_14_agent1
 z_2_14_agent1 z_3_14_agent1 z_0_19_agent1 z_1_19_agent1 z_2_19_agent1
 z_3_19_agent1 z_0_21_agent1 z_1_21_agent1 z_2_21_agent1 z_3_21_agent1
 z_0_23_agent1 z_1_23_agent1 z_2_23_agent1 z_3_23_agent1 z_0_27_agent1
 z_1_27_agent1 z_2_27_agent1 z_3_27_agent1 z_0_35_agent1 z_1_35_agent1
 z_2_35_agent1 z_3_35_agent1 z_0_43_agent1 z_1_43_agent1 z_2_43_agent1
 z_3_43_agent1 z_0_46_agent1 z_1_46_agent1 z_2_46_agent1 z_3_46_agent1
 z_0_48_agent1 z_1_48_agent1 z_2_48_agent1 z_3_48_agent1 z_0_54_agent1
 z_1_54_agent1 z_2_54_agent1 z_3_54_agent1
End
