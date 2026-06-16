\ Model multi_agent_many_to_many
\ LP format - for model browsing. Use MPS format to capture full model detail.
\ Signature: 0x37a86c19597729be
Maximize multi-objectives
  target_directed_reward: Priority=2 Weight=1 AbsTol=0 RelTol=0
   0 u_50_agent0 + 0 u_51_agent0 + 0 u_52_agent0 + 0 u_53_agent0
   + 0 u_54_agent0 + 0 u_55_agent0 + 0 u_56_agent0 + 0 u_58_agent0
   + 0 u_59_agent0 + 0 u_60_agent0 + 0 u_50_agent1 + 0 u_51_agent1
   + 0 u_52_agent1 + 0 u_53_agent1 + 0 u_54_agent1 + 0 u_55_agent1
   + 0 u_56_agent1 + 0 u_58_agent1 + 0 u_59_agent1 + 0 u_60_agent1
   + 0.1 z_1_11_agent0 + 0.9 z_2_11_agent0 + 0.9 z_3_11_agent0
   + 0.3 z_1_0_agent0 + 0.7 z_2_0_agent0 + 0.7 z_3_0_agent0
   + 0.05 z_1_5_agent0 + 0.01 z_2_5_agent0 + 0.01 z_3_5_agent0
   + 0.1166666666666667 z_1_6_agent0 + 0.01 z_2_6_agent0
   + 0.01 z_3_6_agent0 + 0.05 z_1_14_agent0 + 0.01 z_2_14_agent0
   + 0.01 z_3_14_agent0 + 0.1166666666666667 z_1_15_agent0
   + 0.4 z_2_15_agent0 + 0.4 z_3_15_agent0 + 0.05 z_1_16_agent0
   + 0.01 z_2_16_agent0 + 0.01 z_3_16_agent0 + 0.1 z_1_17_agent0
   + 0.01 z_2_17_agent0 + 0.01 z_3_17_agent0
   + 0.1166666666666667 z_1_18_agent0 + 0.4 z_2_18_agent0
   + 0.4 z_3_18_agent0 + 0.1 z_1_19_agent0 + 0.01 z_2_19_agent0
   + 0.01 z_3_19_agent0 + 0.7 z_1_25_agent0 + 0.05 z_2_25_agent0
   + 0.05 z_3_25_agent0 + 0.3 z_1_27_agent0 + 0.01 z_2_27_agent0
   + 0.01 z_3_27_agent0 + 0.3 z_1_35_agent0 + 0.01 z_2_35_agent0
   + 0.01 z_3_35_agent0 + 0.1 z_1_36_agent0 + 0.02 z_2_36_agent0
   + 0.02 z_3_36_agent0 + 0.15 z_1_37_agent0 + 0.05 z_2_37_agent0
   + 0.05 z_3_37_agent0 + 0.1 z_1_38_agent0 + 0.7 z_2_38_agent0
   + 0.7 z_3_38_agent0 + 0.15 z_1_39_agent0 + 0.05 z_2_39_agent0
   + 0.05 z_3_39_agent0 + 0.3 z_1_45_agent0 + 0.01 z_2_45_agent0
   + 0.01 z_3_45_agent0 + 0.1 z_1_48_agent0 + 0.01 z_2_48_agent0
   + 0.01 z_3_48_agent0 + 0.05 z_1_55_agent0 + 0.8 z_2_55_agent0
   + 0.8 z_3_55_agent0 + 0.15 z_1_57_agent0 + 0.1 z_2_57_agent0
   + 0.1 z_3_57_agent0 + 1.5 z_1_60_agent0 + 0.1 z_2_60_agent0
   + 0.1 z_3_60_agent0 + 0.7 z_1_25_agent1 + 0.05 z_2_25_agent1
   + 0.05 z_3_25_agent1 + 0.3 z_1_0_agent1 + 0.7 z_2_0_agent1
   + 0.7 z_3_0_agent1 + 0.05 z_1_5_agent1 + 0.01 z_2_5_agent1
   + 0.01 z_3_5_agent1 + 0.1166666666666667 z_1_6_agent1
   + 0.01 z_2_6_agent1 + 0.01 z_3_6_agent1 + 0.1 z_1_11_agent1
   + 0.9 z_2_11_agent1 + 0.9 z_3_11_agent1 + 0.05 z_1_14_agent1
   + 0.01 z_2_14_agent1 + 0.01 z_3_14_agent1
   + 0.1166666666666667 z_1_15_agent1 + 0.4 z_2_15_agent1
   + 0.4 z_3_15_agent1 + 0.05 z_1_16_agent1 + 0.01 z_2_16_agent1
   + 0.01 z_3_16_agent1 + 0.1 z_1_17_agent1 + 0.01 z_2_17_agent1
   + 0.01 z_3_17_agent1 + 0.1166666666666667 z_1_18_agent1
   + 0.4 z_2_18_agent1 + 0.4 z_3_18_agent1 + 0.1 z_1_19_agent1
   + 0.01 z_2_19_agent1 + 0.01 z_3_19_agent1 + 0.3 z_1_27_agent1
   + 0.01 z_2_27_agent1 + 0.01 z_3_27_agent1 + 0.3 z_1_35_agent1
   + 0.01 z_2_35_agent1 + 0.01 z_3_35_agent1 + 0.1 z_1_36_agent1
   + 0.02 z_2_36_agent1 + 0.02 z_3_36_agent1 + 0.15 z_1_37_agent1
   + 0.05 z_2_37_agent1 + 0.05 z_3_37_agent1 + 0.1 z_1_38_agent1
   + 0.7 z_2_38_agent1 + 0.7 z_3_38_agent1 + 0.15 z_1_39_agent1
   + 0.05 z_2_39_agent1 + 0.05 z_3_39_agent1 + 0.3 z_1_45_agent1
   + 0.01 z_2_45_agent1 + 0.01 z_3_45_agent1 + 0.1 z_1_48_agent1
   + 0.01 z_2_48_agent1 + 0.01 z_3_48_agent1 + 0.05 z_1_55_agent1
   + 0.8 z_2_55_agent1 + 0.8 z_3_55_agent1 + 0.15 z_1_57_agent1
   + 0.1 z_2_57_agent1 + 0.1 z_3_57_agent1 + 1.5 z_1_60_agent1
   + 0.1 z_2_60_agent1 + 0.1 z_3_60_agent1
  target_directed_route_cost: Priority=1 Weight=1 AbsTol=0 RelTol=0
   - 0.00170409489359236 x_0_11_agent0 - 0.00187154930510144 x_0_15_agent0
   - 0.0012685727056759 x_0_18_agent0 - 0.00256739977981773 x_5_40_agent0
   - 0.00190813598324628 x_6_40_agent0 - 0.00170409489359236 x_11_0_agent0
   - 0.0014367307071493 x_11_38_agent0 - 0.00194261189149815 x_14_40_agent0
   - 0.00187154930510144 x_15_0_agent0 - 0.0012713870655332 x_16_29_agent0
   - 0.00282069216697432 x_16_37_agent0
   - 0.00130656656374939 x_17_40_agent0 - 0.0012685727056759 x_18_0_agent0
   - 0.00174912465130909 x_19_40_agent0 - 0.0018996929036744 x_25_37_agent0
   - 0.00239079869877244 x_25_39_agent0
   - 0.00221490120769148 x_27_39_agent0 - 0.0012713870655332 x_29_16_agent0
   - 0.0022951104636244 x_29_37_agent0 - 0.0019735698499284 x_29_39_agent0
   - 0.00257584285938962 x_35_39_agent0
   - 0.00207291354868616 x_35_57_agent0
   - 9.7587928051718004e-04 x_36_38_agent0
   - 6.4026686753470359e-04 x_36_40_agent0
   - 0.00282069216697432 x_37_16_agent0 - 0.0018996929036744 x_37_25_agent0
   - 0.0022951104636244 x_37_29_agent0 - 0.00191868983271114 x_37_39_agent0
   - 0.0014367307071493 x_38_11_agent0
   - 9.7587928051718004e-04 x_38_36_agent0
   - 0.00145009891647146 x_38_40_agent0
   - 0.00239079869877244 x_39_25_agent0
   - 0.00221490120769148 x_39_27_agent0 - 0.0019735698499284 x_39_29_agent0
   - 0.00257584285938962 x_39_35_agent0
   - 0.00191868983271114 x_39_37_agent0
   - 0.00200734216821594 x_39_45_agent0 - 0.00256739977981773 x_40_5_agent0
   - 0.00190813598324628 x_40_6_agent0 - 0.00194261189149815 x_40_14_agent0
   - 0.00130656656374939 x_40_17_agent0
   - 0.00174912465130909 x_40_19_agent0
   - 6.4026686753470359e-04 x_40_36_agent0
   - 0.00145009891647146 x_40_38_agent0
   - 0.00272500393182627 x_40_48_agent0
   - 0.00200734216821594 x_45_39_agent0
   - 0.00272500393182627 x_48_40_agent0
   - 0.00207291354868616 x_57_35_agent0 - 0.00170409489359236 x_0_11_agent1
   - 0.00187154930510144 x_0_15_agent1 - 0.0012685727056759 x_0_18_agent1
   - 0.00256739977981773 x_5_40_agent1 - 0.00190813598324628 x_6_40_agent1
   - 0.00170409489359236 x_11_0_agent1 - 0.0014367307071493 x_11_38_agent1
   - 0.00194261189149815 x_14_40_agent1 - 0.00187154930510144 x_15_0_agent1
   - 0.0012713870655332 x_16_29_agent1 - 0.00282069216697432 x_16_37_agent1
   - 0.00130656656374939 x_17_40_agent1 - 0.0012685727056759 x_18_0_agent1
   - 0.00174912465130909 x_19_40_agent1 - 0.0018996929036744 x_25_37_agent1
   - 0.00239079869877244 x_25_39_agent1
   - 0.00221490120769148 x_27_39_agent1 - 0.0012713870655332 x_29_16_agent1
   - 0.0022951104636244 x_29_37_agent1 - 0.0019735698499284 x_29_39_agent1
   - 0.00257584285938962 x_35_39_agent1
   - 0.00207291354868616 x_35_57_agent1
   - 9.7587928051718004e-04 x_36_38_agent1
   - 6.4026686753470359e-04 x_36_40_agent1
   - 0.00282069216697432 x_37_16_agent1 - 0.0018996929036744 x_37_25_agent1
   - 0.0022951104636244 x_37_29_agent1 - 0.00191868983271114 x_37_39_agent1
   - 0.0014367307071493 x_38_11_agent1
   - 9.7587928051718004e-04 x_38_36_agent1
   - 0.00145009891647146 x_38_40_agent1
   - 0.00239079869877244 x_39_25_agent1
   - 0.00221490120769148 x_39_27_agent1 - 0.0019735698499284 x_39_29_agent1
   - 0.00257584285938962 x_39_35_agent1
   - 0.00191868983271114 x_39_37_agent1
   - 0.00200734216821594 x_39_45_agent1 - 0.00256739977981773 x_40_5_agent1
   - 0.00190813598324628 x_40_6_agent1 - 0.00194261189149815 x_40_14_agent1
   - 0.00130656656374939 x_40_17_agent1
   - 0.00174912465130909 x_40_19_agent1
   - 6.4026686753470359e-04 x_40_36_agent1
   - 0.00145009891647146 x_40_38_agent1
   - 0.00272500393182627 x_40_48_agent1
   - 0.00200734216821594 x_45_39_agent1
   - 0.00272500393182627 x_48_40_agent1
   - 0.00207291354868616 x_57_35_agent1 - 0.024 y_0_agent0
   - 0.048 y_25_agent0 - 0.012 y_29_agent0 - 0.024 y_37_agent0
   - 0.024 y_38_agent0 - 0.024 y_39_agent0 - 0.024 y_40_agent0
   - 0.015 y_55_agent0 - 0.024 y_0_agent1 - 0.036 y_11_agent1
   - 0.012 y_29_agent1 - 0.024 y_37_agent1 - 0.024 y_38_agent1
   - 0.024 y_39_agent1 - 0.024 y_40_agent1 - 0.015 y_55_agent1
   + 0.0513364236108237 Constant1
Subject To
 depart_agent0: x_11_0_agent0 + x_11_38_agent0 = 1
 first_hop_vp_agent0: x_11_0_agent0 + x_11_38_agent0 = 1
 first_hop_grounded_vv_agent0: x_11_0_agent0 + x_11_38_agent0 = 1
 no_return_agent0: x_0_11_agent0 + x_38_11_agent0 = 0
 flow_in_0_agent0: x_11_0_agent0 + x_15_0_agent0 + x_18_0_agent0
   - y_0_agent0 = 0
 flow_out_0_agent0: x_0_11_agent0 + x_0_15_agent0 + x_0_18_agent0
   - y_0_agent0 <= 0
 flow_in_5_agent0: x_40_5_agent0 - y_5_agent0 = 0
 flow_out_5_agent0: x_5_40_agent0 - y_5_agent0 <= 0
 flow_in_6_agent0: x_40_6_agent0 - y_6_agent0 = 0
 flow_out_6_agent0: x_6_40_agent0 - y_6_agent0 <= 0
 flow_in_14_agent0: x_40_14_agent0 - y_14_agent0 = 0
 flow_out_14_agent0: x_14_40_agent0 - y_14_agent0 <= 0
 flow_in_15_agent0: x_0_15_agent0 - y_15_agent0 = 0
 flow_out_15_agent0: x_15_0_agent0 - y_15_agent0 <= 0
 flow_in_16_agent0: x_29_16_agent0 + x_37_16_agent0 - y_16_agent0 = 0
 flow_out_16_agent0: x_16_29_agent0 + x_16_37_agent0 - y_16_agent0 <= 0
 flow_in_17_agent0: x_40_17_agent0 - y_17_agent0 = 0
 flow_out_17_agent0: x_17_40_agent0 - y_17_agent0 <= 0
 flow_in_18_agent0: x_0_18_agent0 - y_18_agent0 = 0
 flow_out_18_agent0: x_18_0_agent0 - y_18_agent0 <= 0
 flow_in_19_agent0: x_40_19_agent0 - y_19_agent0 = 0
 flow_out_19_agent0: x_19_40_agent0 - y_19_agent0 <= 0
 flow_in_25_agent0: x_37_25_agent0 + x_39_25_agent0 - y_25_agent0 = 0
 flow_out_25_agent0: x_25_37_agent0 + x_25_39_agent0 - y_25_agent0 <= 0
 flow_in_27_agent0: x_39_27_agent0 - y_27_agent0 = 0
 flow_out_27_agent0: x_27_39_agent0 - y_27_agent0 <= 0
 flow_in_29_agent0: x_16_29_agent0 + x_37_29_agent0 + x_39_29_agent0
   - y_29_agent0 = 0
 flow_out_29_agent0: x_29_16_agent0 + x_29_37_agent0 + x_29_39_agent0
   - y_29_agent0 <= 0
 flow_in_35_agent0: x_39_35_agent0 + x_57_35_agent0 - y_35_agent0 = 0
 flow_out_35_agent0: x_35_39_agent0 + x_35_57_agent0 - y_35_agent0 <= 0
 flow_in_36_agent0: x_38_36_agent0 + x_40_36_agent0 - y_36_agent0 = 0
 flow_out_36_agent0: x_36_38_agent0 + x_36_40_agent0 - y_36_agent0 <= 0
 flow_in_37_agent0: x_16_37_agent0 + x_25_37_agent0 + x_29_37_agent0
   + x_39_37_agent0 - y_37_agent0 = 0
 flow_out_37_agent0: x_37_16_agent0 + x_37_25_agent0 + x_37_29_agent0
   + x_37_39_agent0 - y_37_agent0 <= 0
 flow_in_38_agent0: x_11_38_agent0 + x_36_38_agent0 + x_40_38_agent0
   - y_38_agent0 = 0
 flow_out_38_agent0: x_38_11_agent0 + x_38_36_agent0 + x_38_40_agent0
   - y_38_agent0 <= 0
 flow_in_39_agent0: x_25_39_agent0 + x_27_39_agent0 + x_29_39_agent0
   + x_35_39_agent0 + x_37_39_agent0 + x_45_39_agent0 - y_39_agent0 = 0
 flow_out_39_agent0: x_39_25_agent0 + x_39_27_agent0 + x_39_29_agent0
   + x_39_35_agent0 + x_39_37_agent0 + x_39_45_agent0 - y_39_agent0 <= 0
 flow_in_40_agent0: x_5_40_agent0 + x_6_40_agent0 + x_14_40_agent0
   + x_17_40_agent0 + x_19_40_agent0 + x_36_40_agent0 + x_38_40_agent0
   + x_48_40_agent0 - y_40_agent0 = 0
 flow_out_40_agent0: x_40_5_agent0 + x_40_6_agent0 + x_40_14_agent0
   + x_40_17_agent0 + x_40_19_agent0 + x_40_36_agent0 + x_40_38_agent0
   + x_40_48_agent0 - y_40_agent0 <= 0
 flow_in_45_agent0: x_39_45_agent0 - y_45_agent0 = 0
 flow_out_45_agent0: x_45_39_agent0 - y_45_agent0 <= 0
 flow_in_48_agent0: x_40_48_agent0 - y_48_agent0 = 0
 flow_out_48_agent0: x_48_40_agent0 - y_48_agent0 <= 0
 flow_in_50_agent0: - y_50_agent0 = 0
 flow_out_50_agent0: - y_50_agent0 <= 0
 flow_in_51_agent0: - y_51_agent0 = 0
 flow_out_51_agent0: - y_51_agent0 <= 0
 flow_in_52_agent0: - y_52_agent0 = 0
 flow_out_52_agent0: - y_52_agent0 <= 0
 flow_in_53_agent0: - y_53_agent0 = 0
 flow_out_53_agent0: - y_53_agent0 <= 0
 flow_in_54_agent0: - y_54_agent0 = 0
 flow_out_54_agent0: - y_54_agent0 <= 0
 flow_in_55_agent0: - y_55_agent0 = 0
 flow_out_55_agent0: - y_55_agent0 <= 0
 flow_in_56_agent0: - y_56_agent0 = 0
 flow_out_56_agent0: - y_56_agent0 <= 0
 flow_in_57_agent0: x_35_57_agent0 - y_57_agent0 = 0
 flow_out_57_agent0: x_57_35_agent0 - y_57_agent0 <= 0
 flow_in_58_agent0: - y_58_agent0 = 0
 flow_out_58_agent0: - y_58_agent0 <= 0
 flow_in_59_agent0: - y_59_agent0 = 0
 flow_out_59_agent0: - y_59_agent0 <= 0
 flow_in_60_agent0: - y_60_agent0 = 0
 flow_out_60_agent0: - y_60_agent0 <= 0
 target_reward_visit_0_0_agent0: - y_0_agent0 + z_0_0_agent0 <= 0
 target_reward_visit_1_0_agent0: - y_0_agent0 + z_1_0_agent0 <= 0
 target_reward_visit_2_0_agent0: - y_0_agent0 + z_2_0_agent0 <= 0
 target_reward_visit_3_0_agent0: - y_0_agent0 + z_3_0_agent0 <= 0
 target_reward_visit_0_5_agent0: - y_5_agent0 + z_0_5_agent0 <= 0
 target_reward_visit_1_5_agent0: - y_5_agent0 + z_1_5_agent0 <= 0
 target_reward_visit_2_5_agent0: - y_5_agent0 + z_2_5_agent0 <= 0
 target_reward_visit_3_5_agent0: - y_5_agent0 + z_3_5_agent0 <= 0
 target_reward_visit_0_6_agent0: - y_6_agent0 + z_0_6_agent0 <= 0
 target_reward_visit_1_6_agent0: - y_6_agent0 + z_1_6_agent0 <= 0
 target_reward_visit_2_6_agent0: - y_6_agent0 + z_2_6_agent0 <= 0
 target_reward_visit_3_6_agent0: - y_6_agent0 + z_3_6_agent0 <= 0
 target_reward_visit_0_14_agent0: - y_14_agent0 + z_0_14_agent0 <= 0
 target_reward_visit_1_14_agent0: - y_14_agent0 + z_1_14_agent0 <= 0
 target_reward_visit_2_14_agent0: - y_14_agent0 + z_2_14_agent0 <= 0
 target_reward_visit_3_14_agent0: - y_14_agent0 + z_3_14_agent0 <= 0
 target_reward_visit_0_15_agent0: - y_15_agent0 + z_0_15_agent0 <= 0
 target_reward_visit_1_15_agent0: - y_15_agent0 + z_1_15_agent0 <= 0
 target_reward_visit_2_15_agent0: - y_15_agent0 + z_2_15_agent0 <= 0
 target_reward_visit_3_15_agent0: - y_15_agent0 + z_3_15_agent0 <= 0
 target_reward_visit_0_16_agent0: - y_16_agent0 + z_0_16_agent0 <= 0
 target_reward_visit_1_16_agent0: - y_16_agent0 + z_1_16_agent0 <= 0
 target_reward_visit_2_16_agent0: - y_16_agent0 + z_2_16_agent0 <= 0
 target_reward_visit_3_16_agent0: - y_16_agent0 + z_3_16_agent0 <= 0
 target_reward_visit_0_17_agent0: - y_17_agent0 + z_0_17_agent0 <= 0
 target_reward_visit_1_17_agent0: - y_17_agent0 + z_1_17_agent0 <= 0
 target_reward_visit_2_17_agent0: - y_17_agent0 + z_2_17_agent0 <= 0
 target_reward_visit_3_17_agent0: - y_17_agent0 + z_3_17_agent0 <= 0
 target_reward_visit_0_18_agent0: - y_18_agent0 + z_0_18_agent0 <= 0
 target_reward_visit_1_18_agent0: - y_18_agent0 + z_1_18_agent0 <= 0
 target_reward_visit_2_18_agent0: - y_18_agent0 + z_2_18_agent0 <= 0
 target_reward_visit_3_18_agent0: - y_18_agent0 + z_3_18_agent0 <= 0
 target_reward_visit_0_19_agent0: - y_19_agent0 + z_0_19_agent0 <= 0
 target_reward_visit_1_19_agent0: - y_19_agent0 + z_1_19_agent0 <= 0
 target_reward_visit_2_19_agent0: - y_19_agent0 + z_2_19_agent0 <= 0
 target_reward_visit_3_19_agent0: - y_19_agent0 + z_3_19_agent0 <= 0
 target_reward_visit_0_25_agent0: - y_25_agent0 + z_0_25_agent0 <= 0
 target_reward_visit_1_25_agent0: - y_25_agent0 + z_1_25_agent0 <= 0
 target_reward_visit_2_25_agent0: - y_25_agent0 + z_2_25_agent0 <= 0
 target_reward_visit_3_25_agent0: - y_25_agent0 + z_3_25_agent0 <= 0
 target_reward_visit_0_27_agent0: - y_27_agent0 + z_0_27_agent0 <= 0
 target_reward_visit_1_27_agent0: - y_27_agent0 + z_1_27_agent0 <= 0
 target_reward_visit_2_27_agent0: - y_27_agent0 + z_2_27_agent0 <= 0
 target_reward_visit_3_27_agent0: - y_27_agent0 + z_3_27_agent0 <= 0
 target_reward_visit_0_29_agent0: - y_29_agent0 + z_0_29_agent0 <= 0
 target_reward_visit_1_29_agent0: - y_29_agent0 + z_1_29_agent0 <= 0
 target_reward_visit_2_29_agent0: - y_29_agent0 + z_2_29_agent0 <= 0
 target_reward_visit_3_29_agent0: - y_29_agent0 + z_3_29_agent0 <= 0
 target_reward_visit_0_35_agent0: - y_35_agent0 + z_0_35_agent0 <= 0
 target_reward_visit_1_35_agent0: - y_35_agent0 + z_1_35_agent0 <= 0
 target_reward_visit_2_35_agent0: - y_35_agent0 + z_2_35_agent0 <= 0
 target_reward_visit_3_35_agent0: - y_35_agent0 + z_3_35_agent0 <= 0
 target_reward_visit_0_36_agent0: - y_36_agent0 + z_0_36_agent0 <= 0
 target_reward_visit_1_36_agent0: - y_36_agent0 + z_1_36_agent0 <= 0
 target_reward_visit_2_36_agent0: - y_36_agent0 + z_2_36_agent0 <= 0
 target_reward_visit_3_36_agent0: - y_36_agent0 + z_3_36_agent0 <= 0
 target_reward_visit_0_37_agent0: - y_37_agent0 + z_0_37_agent0 <= 0
 target_reward_visit_1_37_agent0: - y_37_agent0 + z_1_37_agent0 <= 0
 target_reward_visit_2_37_agent0: - y_37_agent0 + z_2_37_agent0 <= 0
 target_reward_visit_3_37_agent0: - y_37_agent0 + z_3_37_agent0 <= 0
 target_reward_visit_0_38_agent0: - y_38_agent0 + z_0_38_agent0 <= 0
 target_reward_visit_1_38_agent0: - y_38_agent0 + z_1_38_agent0 <= 0
 target_reward_visit_2_38_agent0: - y_38_agent0 + z_2_38_agent0 <= 0
 target_reward_visit_3_38_agent0: - y_38_agent0 + z_3_38_agent0 <= 0
 target_reward_visit_0_39_agent0: - y_39_agent0 + z_0_39_agent0 <= 0
 target_reward_visit_1_39_agent0: - y_39_agent0 + z_1_39_agent0 <= 0
 target_reward_visit_2_39_agent0: - y_39_agent0 + z_2_39_agent0 <= 0
 target_reward_visit_3_39_agent0: - y_39_agent0 + z_3_39_agent0 <= 0
 target_reward_visit_0_40_agent0: - y_40_agent0 + z_0_40_agent0 <= 0
 target_reward_visit_1_40_agent0: - y_40_agent0 + z_1_40_agent0 <= 0
 target_reward_visit_2_40_agent0: - y_40_agent0 + z_2_40_agent0 <= 0
 target_reward_visit_3_40_agent0: - y_40_agent0 + z_3_40_agent0 <= 0
 target_reward_visit_0_45_agent0: - y_45_agent0 + z_0_45_agent0 <= 0
 target_reward_visit_1_45_agent0: - y_45_agent0 + z_1_45_agent0 <= 0
 target_reward_visit_2_45_agent0: - y_45_agent0 + z_2_45_agent0 <= 0
 target_reward_visit_3_45_agent0: - y_45_agent0 + z_3_45_agent0 <= 0
 target_reward_visit_0_48_agent0: - y_48_agent0 + z_0_48_agent0 <= 0
 target_reward_visit_1_48_agent0: - y_48_agent0 + z_1_48_agent0 <= 0
 target_reward_visit_2_48_agent0: - y_48_agent0 + z_2_48_agent0 <= 0
 target_reward_visit_3_48_agent0: - y_48_agent0 + z_3_48_agent0 <= 0
 target_reward_visit_0_50_agent0: - y_50_agent0 + z_0_50_agent0 <= 0
 target_reward_visit_1_50_agent0: - y_50_agent0 + z_1_50_agent0 <= 0
 target_reward_visit_2_50_agent0: - y_50_agent0 + z_2_50_agent0 <= 0
 target_reward_visit_3_50_agent0: - y_50_agent0 + z_3_50_agent0 <= 0
 target_reward_visit_0_51_agent0: - y_51_agent0 + z_0_51_agent0 <= 0
 target_reward_visit_1_51_agent0: - y_51_agent0 + z_1_51_agent0 <= 0
 target_reward_visit_2_51_agent0: - y_51_agent0 + z_2_51_agent0 <= 0
 target_reward_visit_3_51_agent0: - y_51_agent0 + z_3_51_agent0 <= 0
 target_reward_visit_0_52_agent0: - y_52_agent0 + z_0_52_agent0 <= 0
 target_reward_visit_1_52_agent0: - y_52_agent0 + z_1_52_agent0 <= 0
 target_reward_visit_2_52_agent0: - y_52_agent0 + z_2_52_agent0 <= 0
 target_reward_visit_3_52_agent0: - y_52_agent0 + z_3_52_agent0 <= 0
 target_reward_visit_0_53_agent0: - y_53_agent0 + z_0_53_agent0 <= 0
 target_reward_visit_1_53_agent0: - y_53_agent0 + z_1_53_agent0 <= 0
 target_reward_visit_2_53_agent0: - y_53_agent0 + z_2_53_agent0 <= 0
 target_reward_visit_3_53_agent0: - y_53_agent0 + z_3_53_agent0 <= 0
 target_reward_visit_0_54_agent0: - y_54_agent0 + z_0_54_agent0 <= 0
 target_reward_visit_1_54_agent0: - y_54_agent0 + z_1_54_agent0 <= 0
 target_reward_visit_2_54_agent0: - y_54_agent0 + z_2_54_agent0 <= 0
 target_reward_visit_3_54_agent0: - y_54_agent0 + z_3_54_agent0 <= 0
 target_reward_visit_0_55_agent0: - y_55_agent0 + z_0_55_agent0 <= 0
 target_reward_visit_1_55_agent0: - y_55_agent0 + z_1_55_agent0 <= 0
 target_reward_visit_2_55_agent0: - y_55_agent0 + z_2_55_agent0 <= 0
 target_reward_visit_3_55_agent0: - y_55_agent0 + z_3_55_agent0 <= 0
 target_reward_visit_0_56_agent0: - y_56_agent0 + z_0_56_agent0 <= 0
 target_reward_visit_1_56_agent0: - y_56_agent0 + z_1_56_agent0 <= 0
 target_reward_visit_2_56_agent0: - y_56_agent0 + z_2_56_agent0 <= 0
 target_reward_visit_3_56_agent0: - y_56_agent0 + z_3_56_agent0 <= 0
 target_reward_visit_0_57_agent0: - y_57_agent0 + z_0_57_agent0 <= 0
 target_reward_visit_1_57_agent0: - y_57_agent0 + z_1_57_agent0 <= 0
 target_reward_visit_2_57_agent0: - y_57_agent0 + z_2_57_agent0 <= 0
 target_reward_visit_3_57_agent0: - y_57_agent0 + z_3_57_agent0 <= 0
 target_reward_visit_0_58_agent0: - y_58_agent0 + z_0_58_agent0 <= 0
 target_reward_visit_1_58_agent0: - y_58_agent0 + z_1_58_agent0 <= 0
 target_reward_visit_2_58_agent0: - y_58_agent0 + z_2_58_agent0 <= 0
 target_reward_visit_3_58_agent0: - y_58_agent0 + z_3_58_agent0 <= 0
 target_reward_visit_0_59_agent0: - y_59_agent0 + z_0_59_agent0 <= 0
 target_reward_visit_1_59_agent0: - y_59_agent0 + z_1_59_agent0 <= 0
 target_reward_visit_2_59_agent0: - y_59_agent0 + z_2_59_agent0 <= 0
 target_reward_visit_3_59_agent0: - y_59_agent0 + z_3_59_agent0 <= 0
 target_reward_visit_0_60_agent0: - y_60_agent0 + z_0_60_agent0 <= 0
 target_reward_visit_1_60_agent0: - y_60_agent0 + z_1_60_agent0 <= 0
 target_reward_visit_2_60_agent0: - y_60_agent0 + z_2_60_agent0 <= 0
 target_reward_visit_3_60_agent0: - y_60_agent0 + z_3_60_agent0 <= 0
 mtz_0_11_agent0: 32 x_0_11_agent0 + u_0_agent0 - u_11_agent0 <= 31
 mtz_0_15_agent0: 32 x_0_15_agent0 + u_0_agent0 - u_15_agent0 <= 31
 mtz_0_18_agent0: 32 x_0_18_agent0 + u_0_agent0 - u_18_agent0 <= 31
 mtz_5_40_agent0: 32 x_5_40_agent0 + u_5_agent0 - u_40_agent0 <= 31
 mtz_6_40_agent0: 32 x_6_40_agent0 + u_6_agent0 - u_40_agent0 <= 31
 mtz_11_0_agent0: 32 x_11_0_agent0 - u_0_agent0 + u_11_agent0 <= 31
 mtz_11_38_agent0: 32 x_11_38_agent0 + u_11_agent0 - u_38_agent0 <= 31
 mtz_14_40_agent0: 32 x_14_40_agent0 + u_14_agent0 - u_40_agent0 <= 31
 mtz_15_0_agent0: 32 x_15_0_agent0 - u_0_agent0 + u_15_agent0 <= 31
 mtz_16_29_agent0: 32 x_16_29_agent0 + u_16_agent0 - u_29_agent0 <= 31
 mtz_16_37_agent0: 32 x_16_37_agent0 + u_16_agent0 - u_37_agent0 <= 31
 mtz_17_40_agent0: 32 x_17_40_agent0 + u_17_agent0 - u_40_agent0 <= 31
 mtz_18_0_agent0: 32 x_18_0_agent0 - u_0_agent0 + u_18_agent0 <= 31
 mtz_19_40_agent0: 32 x_19_40_agent0 + u_19_agent0 - u_40_agent0 <= 31
 mtz_25_37_agent0: 32 x_25_37_agent0 + u_25_agent0 - u_37_agent0 <= 31
 mtz_25_39_agent0: 32 x_25_39_agent0 + u_25_agent0 - u_39_agent0 <= 31
 mtz_27_39_agent0: 32 x_27_39_agent0 + u_27_agent0 - u_39_agent0 <= 31
 mtz_29_16_agent0: 32 x_29_16_agent0 - u_16_agent0 + u_29_agent0 <= 31
 mtz_29_37_agent0: 32 x_29_37_agent0 + u_29_agent0 - u_37_agent0 <= 31
 mtz_29_39_agent0: 32 x_29_39_agent0 + u_29_agent0 - u_39_agent0 <= 31
 mtz_35_39_agent0: 32 x_35_39_agent0 + u_35_agent0 - u_39_agent0 <= 31
 mtz_35_57_agent0: 32 x_35_57_agent0 + u_35_agent0 - u_57_agent0 <= 31
 mtz_36_38_agent0: 32 x_36_38_agent0 + u_36_agent0 - u_38_agent0 <= 31
 mtz_36_40_agent0: 32 x_36_40_agent0 + u_36_agent0 - u_40_agent0 <= 31
 mtz_37_16_agent0: 32 x_37_16_agent0 - u_16_agent0 + u_37_agent0 <= 31
 mtz_37_25_agent0: 32 x_37_25_agent0 - u_25_agent0 + u_37_agent0 <= 31
 mtz_37_29_agent0: 32 x_37_29_agent0 - u_29_agent0 + u_37_agent0 <= 31
 mtz_37_39_agent0: 32 x_37_39_agent0 + u_37_agent0 - u_39_agent0 <= 31
 mtz_38_11_agent0: 32 x_38_11_agent0 - u_11_agent0 + u_38_agent0 <= 31
 mtz_38_36_agent0: 32 x_38_36_agent0 - u_36_agent0 + u_38_agent0 <= 31
 mtz_38_40_agent0: 32 x_38_40_agent0 + u_38_agent0 - u_40_agent0 <= 31
 mtz_39_25_agent0: 32 x_39_25_agent0 - u_25_agent0 + u_39_agent0 <= 31
 mtz_39_27_agent0: 32 x_39_27_agent0 - u_27_agent0 + u_39_agent0 <= 31
 mtz_39_29_agent0: 32 x_39_29_agent0 - u_29_agent0 + u_39_agent0 <= 31
 mtz_39_35_agent0: 32 x_39_35_agent0 - u_35_agent0 + u_39_agent0 <= 31
 mtz_39_37_agent0: 32 x_39_37_agent0 - u_37_agent0 + u_39_agent0 <= 31
 mtz_39_45_agent0: 32 x_39_45_agent0 + u_39_agent0 - u_45_agent0 <= 31
 mtz_40_5_agent0: 32 x_40_5_agent0 - u_5_agent0 + u_40_agent0 <= 31
 mtz_40_6_agent0: 32 x_40_6_agent0 - u_6_agent0 + u_40_agent0 <= 31
 mtz_40_14_agent0: 32 x_40_14_agent0 - u_14_agent0 + u_40_agent0 <= 31
 mtz_40_17_agent0: 32 x_40_17_agent0 - u_17_agent0 + u_40_agent0 <= 31
 mtz_40_19_agent0: 32 x_40_19_agent0 - u_19_agent0 + u_40_agent0 <= 31
 mtz_40_36_agent0: 32 x_40_36_agent0 - u_36_agent0 + u_40_agent0 <= 31
 mtz_40_38_agent0: 32 x_40_38_agent0 - u_38_agent0 + u_40_agent0 <= 31
 mtz_40_48_agent0: 32 x_40_48_agent0 + u_40_agent0 - u_48_agent0 <= 31
 mtz_45_39_agent0: 32 x_45_39_agent0 - u_39_agent0 + u_45_agent0 <= 31
 mtz_48_40_agent0: 32 x_48_40_agent0 - u_40_agent0 + u_48_agent0 <= 31
 mtz_57_35_agent0: 32 x_57_35_agent0 - u_35_agent0 + u_57_agent0 <= 31
 depart_agent1: x_25_37_agent1 + x_25_39_agent1 = 1
 first_hop_vp_agent1: x_25_37_agent1 + x_25_39_agent1 = 1
 first_hop_grounded_vv_agent1: x_25_37_agent1 + x_25_39_agent1 = 1
 no_return_agent1: x_37_25_agent1 + x_39_25_agent1 = 0
 flow_in_0_agent1: x_11_0_agent1 + x_15_0_agent1 + x_18_0_agent1
   - y_0_agent1 = 0
 flow_out_0_agent1: x_0_11_agent1 + x_0_15_agent1 + x_0_18_agent1
   - y_0_agent1 <= 0
 flow_in_5_agent1: x_40_5_agent1 - y_5_agent1 = 0
 flow_out_5_agent1: x_5_40_agent1 - y_5_agent1 <= 0
 flow_in_6_agent1: x_40_6_agent1 - y_6_agent1 = 0
 flow_out_6_agent1: x_6_40_agent1 - y_6_agent1 <= 0
 flow_in_11_agent1: x_0_11_agent1 + x_38_11_agent1 - y_11_agent1 = 0
 flow_out_11_agent1: x_11_0_agent1 + x_11_38_agent1 - y_11_agent1 <= 0
 flow_in_14_agent1: x_40_14_agent1 - y_14_agent1 = 0
 flow_out_14_agent1: x_14_40_agent1 - y_14_agent1 <= 0
 flow_in_15_agent1: x_0_15_agent1 - y_15_agent1 = 0
 flow_out_15_agent1: x_15_0_agent1 - y_15_agent1 <= 0
 flow_in_16_agent1: x_29_16_agent1 + x_37_16_agent1 - y_16_agent1 = 0
 flow_out_16_agent1: x_16_29_agent1 + x_16_37_agent1 - y_16_agent1 <= 0
 flow_in_17_agent1: x_40_17_agent1 - y_17_agent1 = 0
 flow_out_17_agent1: x_17_40_agent1 - y_17_agent1 <= 0
 flow_in_18_agent1: x_0_18_agent1 - y_18_agent1 = 0
 flow_out_18_agent1: x_18_0_agent1 - y_18_agent1 <= 0
 flow_in_19_agent1: x_40_19_agent1 - y_19_agent1 = 0
 flow_out_19_agent1: x_19_40_agent1 - y_19_agent1 <= 0
 flow_in_27_agent1: x_39_27_agent1 - y_27_agent1 = 0
 flow_out_27_agent1: x_27_39_agent1 - y_27_agent1 <= 0
 flow_in_29_agent1: x_16_29_agent1 + x_37_29_agent1 + x_39_29_agent1
   - y_29_agent1 = 0
 flow_out_29_agent1: x_29_16_agent1 + x_29_37_agent1 + x_29_39_agent1
   - y_29_agent1 <= 0
 flow_in_35_agent1: x_39_35_agent1 + x_57_35_agent1 - y_35_agent1 = 0
 flow_out_35_agent1: x_35_39_agent1 + x_35_57_agent1 - y_35_agent1 <= 0
 flow_in_36_agent1: x_38_36_agent1 + x_40_36_agent1 - y_36_agent1 = 0
 flow_out_36_agent1: x_36_38_agent1 + x_36_40_agent1 - y_36_agent1 <= 0
 flow_in_37_agent1: x_16_37_agent1 + x_25_37_agent1 + x_29_37_agent1
   + x_39_37_agent1 - y_37_agent1 = 0
 flow_out_37_agent1: x_37_16_agent1 + x_37_25_agent1 + x_37_29_agent1
   + x_37_39_agent1 - y_37_agent1 <= 0
 flow_in_38_agent1: x_11_38_agent1 + x_36_38_agent1 + x_40_38_agent1
   - y_38_agent1 = 0
 flow_out_38_agent1: x_38_11_agent1 + x_38_36_agent1 + x_38_40_agent1
   - y_38_agent1 <= 0
 flow_in_39_agent1: x_25_39_agent1 + x_27_39_agent1 + x_29_39_agent1
   + x_35_39_agent1 + x_37_39_agent1 + x_45_39_agent1 - y_39_agent1 = 0
 flow_out_39_agent1: x_39_25_agent1 + x_39_27_agent1 + x_39_29_agent1
   + x_39_35_agent1 + x_39_37_agent1 + x_39_45_agent1 - y_39_agent1 <= 0
 flow_in_40_agent1: x_5_40_agent1 + x_6_40_agent1 + x_14_40_agent1
   + x_17_40_agent1 + x_19_40_agent1 + x_36_40_agent1 + x_38_40_agent1
   + x_48_40_agent1 - y_40_agent1 = 0
 flow_out_40_agent1: x_40_5_agent1 + x_40_6_agent1 + x_40_14_agent1
   + x_40_17_agent1 + x_40_19_agent1 + x_40_36_agent1 + x_40_38_agent1
   + x_40_48_agent1 - y_40_agent1 <= 0
 flow_in_45_agent1: x_39_45_agent1 - y_45_agent1 = 0
 flow_out_45_agent1: x_45_39_agent1 - y_45_agent1 <= 0
 flow_in_48_agent1: x_40_48_agent1 - y_48_agent1 = 0
 flow_out_48_agent1: x_48_40_agent1 - y_48_agent1 <= 0
 flow_in_50_agent1: - y_50_agent1 = 0
 flow_out_50_agent1: - y_50_agent1 <= 0
 flow_in_51_agent1: - y_51_agent1 = 0
 flow_out_51_agent1: - y_51_agent1 <= 0
 flow_in_52_agent1: - y_52_agent1 = 0
 flow_out_52_agent1: - y_52_agent1 <= 0
 flow_in_53_agent1: - y_53_agent1 = 0
 flow_out_53_agent1: - y_53_agent1 <= 0
 flow_in_54_agent1: - y_54_agent1 = 0
 flow_out_54_agent1: - y_54_agent1 <= 0
 flow_in_55_agent1: - y_55_agent1 = 0
 flow_out_55_agent1: - y_55_agent1 <= 0
 flow_in_56_agent1: - y_56_agent1 = 0
 flow_out_56_agent1: - y_56_agent1 <= 0
 flow_in_57_agent1: x_35_57_agent1 - y_57_agent1 = 0
 flow_out_57_agent1: x_57_35_agent1 - y_57_agent1 <= 0
 flow_in_58_agent1: - y_58_agent1 = 0
 flow_out_58_agent1: - y_58_agent1 <= 0
 flow_in_59_agent1: - y_59_agent1 = 0
 flow_out_59_agent1: - y_59_agent1 <= 0
 flow_in_60_agent1: - y_60_agent1 = 0
 flow_out_60_agent1: - y_60_agent1 <= 0
 target_reward_visit_0_0_agent1: - y_0_agent1 + z_0_0_agent1 <= 0
 target_reward_visit_1_0_agent1: - y_0_agent1 + z_1_0_agent1 <= 0
 target_reward_visit_2_0_agent1: - y_0_agent1 + z_2_0_agent1 <= 0
 target_reward_visit_3_0_agent1: - y_0_agent1 + z_3_0_agent1 <= 0
 target_reward_visit_0_5_agent1: - y_5_agent1 + z_0_5_agent1 <= 0
 target_reward_visit_1_5_agent1: - y_5_agent1 + z_1_5_agent1 <= 0
 target_reward_visit_2_5_agent1: - y_5_agent1 + z_2_5_agent1 <= 0
 target_reward_visit_3_5_agent1: - y_5_agent1 + z_3_5_agent1 <= 0
 target_reward_visit_0_6_agent1: - y_6_agent1 + z_0_6_agent1 <= 0
 target_reward_visit_1_6_agent1: - y_6_agent1 + z_1_6_agent1 <= 0
 target_reward_visit_2_6_agent1: - y_6_agent1 + z_2_6_agent1 <= 0
 target_reward_visit_3_6_agent1: - y_6_agent1 + z_3_6_agent1 <= 0
 target_reward_visit_0_11_agent1: - y_11_agent1 + z_0_11_agent1 <= 0
 target_reward_visit_1_11_agent1: - y_11_agent1 + z_1_11_agent1 <= 0
 target_reward_visit_2_11_agent1: - y_11_agent1 + z_2_11_agent1 <= 0
 target_reward_visit_3_11_agent1: - y_11_agent1 + z_3_11_agent1 <= 0
 target_reward_visit_0_14_agent1: - y_14_agent1 + z_0_14_agent1 <= 0
 target_reward_visit_1_14_agent1: - y_14_agent1 + z_1_14_agent1 <= 0
 target_reward_visit_2_14_agent1: - y_14_agent1 + z_2_14_agent1 <= 0
 target_reward_visit_3_14_agent1: - y_14_agent1 + z_3_14_agent1 <= 0
 target_reward_visit_0_15_agent1: - y_15_agent1 + z_0_15_agent1 <= 0
 target_reward_visit_1_15_agent1: - y_15_agent1 + z_1_15_agent1 <= 0
 target_reward_visit_2_15_agent1: - y_15_agent1 + z_2_15_agent1 <= 0
 target_reward_visit_3_15_agent1: - y_15_agent1 + z_3_15_agent1 <= 0
 target_reward_visit_0_16_agent1: - y_16_agent1 + z_0_16_agent1 <= 0
 target_reward_visit_1_16_agent1: - y_16_agent1 + z_1_16_agent1 <= 0
 target_reward_visit_2_16_agent1: - y_16_agent1 + z_2_16_agent1 <= 0
 target_reward_visit_3_16_agent1: - y_16_agent1 + z_3_16_agent1 <= 0
 target_reward_visit_0_17_agent1: - y_17_agent1 + z_0_17_agent1 <= 0
 target_reward_visit_1_17_agent1: - y_17_agent1 + z_1_17_agent1 <= 0
 target_reward_visit_2_17_agent1: - y_17_agent1 + z_2_17_agent1 <= 0
 target_reward_visit_3_17_agent1: - y_17_agent1 + z_3_17_agent1 <= 0
 target_reward_visit_0_18_agent1: - y_18_agent1 + z_0_18_agent1 <= 0
 target_reward_visit_1_18_agent1: - y_18_agent1 + z_1_18_agent1 <= 0
 target_reward_visit_2_18_agent1: - y_18_agent1 + z_2_18_agent1 <= 0
 target_reward_visit_3_18_agent1: - y_18_agent1 + z_3_18_agent1 <= 0
 target_reward_visit_0_19_agent1: - y_19_agent1 + z_0_19_agent1 <= 0
 target_reward_visit_1_19_agent1: - y_19_agent1 + z_1_19_agent1 <= 0
 target_reward_visit_2_19_agent1: - y_19_agent1 + z_2_19_agent1 <= 0
 target_reward_visit_3_19_agent1: - y_19_agent1 + z_3_19_agent1 <= 0
 target_reward_visit_0_27_agent1: - y_27_agent1 + z_0_27_agent1 <= 0
 target_reward_visit_1_27_agent1: - y_27_agent1 + z_1_27_agent1 <= 0
 target_reward_visit_2_27_agent1: - y_27_agent1 + z_2_27_agent1 <= 0
 target_reward_visit_3_27_agent1: - y_27_agent1 + z_3_27_agent1 <= 0
 target_reward_visit_0_29_agent1: - y_29_agent1 + z_0_29_agent1 <= 0
 target_reward_visit_1_29_agent1: - y_29_agent1 + z_1_29_agent1 <= 0
 target_reward_visit_2_29_agent1: - y_29_agent1 + z_2_29_agent1 <= 0
 target_reward_visit_3_29_agent1: - y_29_agent1 + z_3_29_agent1 <= 0
 target_reward_visit_0_35_agent1: - y_35_agent1 + z_0_35_agent1 <= 0
 target_reward_visit_1_35_agent1: - y_35_agent1 + z_1_35_agent1 <= 0
 target_reward_visit_2_35_agent1: - y_35_agent1 + z_2_35_agent1 <= 0
 target_reward_visit_3_35_agent1: - y_35_agent1 + z_3_35_agent1 <= 0
 target_reward_visit_0_36_agent1: - y_36_agent1 + z_0_36_agent1 <= 0
 target_reward_visit_1_36_agent1: - y_36_agent1 + z_1_36_agent1 <= 0
 target_reward_visit_2_36_agent1: - y_36_agent1 + z_2_36_agent1 <= 0
 target_reward_visit_3_36_agent1: - y_36_agent1 + z_3_36_agent1 <= 0
 target_reward_visit_0_37_agent1: - y_37_agent1 + z_0_37_agent1 <= 0
 target_reward_visit_1_37_agent1: - y_37_agent1 + z_1_37_agent1 <= 0
 target_reward_visit_2_37_agent1: - y_37_agent1 + z_2_37_agent1 <= 0
 target_reward_visit_3_37_agent1: - y_37_agent1 + z_3_37_agent1 <= 0
 target_reward_visit_0_38_agent1: - y_38_agent1 + z_0_38_agent1 <= 0
 target_reward_visit_1_38_agent1: - y_38_agent1 + z_1_38_agent1 <= 0
 target_reward_visit_2_38_agent1: - y_38_agent1 + z_2_38_agent1 <= 0
 target_reward_visit_3_38_agent1: - y_38_agent1 + z_3_38_agent1 <= 0
 target_reward_visit_0_39_agent1: - y_39_agent1 + z_0_39_agent1 <= 0
 target_reward_visit_1_39_agent1: - y_39_agent1 + z_1_39_agent1 <= 0
 target_reward_visit_2_39_agent1: - y_39_agent1 + z_2_39_agent1 <= 0
 target_reward_visit_3_39_agent1: - y_39_agent1 + z_3_39_agent1 <= 0
 target_reward_visit_0_40_agent1: - y_40_agent1 + z_0_40_agent1 <= 0
 target_reward_visit_1_40_agent1: - y_40_agent1 + z_1_40_agent1 <= 0
 target_reward_visit_2_40_agent1: - y_40_agent1 + z_2_40_agent1 <= 0
 target_reward_visit_3_40_agent1: - y_40_agent1 + z_3_40_agent1 <= 0
 target_reward_visit_0_45_agent1: - y_45_agent1 + z_0_45_agent1 <= 0
 target_reward_visit_1_45_agent1: - y_45_agent1 + z_1_45_agent1 <= 0
 target_reward_visit_2_45_agent1: - y_45_agent1 + z_2_45_agent1 <= 0
 target_reward_visit_3_45_agent1: - y_45_agent1 + z_3_45_agent1 <= 0
 target_reward_visit_0_48_agent1: - y_48_agent1 + z_0_48_agent1 <= 0
 target_reward_visit_1_48_agent1: - y_48_agent1 + z_1_48_agent1 <= 0
 target_reward_visit_2_48_agent1: - y_48_agent1 + z_2_48_agent1 <= 0
 target_reward_visit_3_48_agent1: - y_48_agent1 + z_3_48_agent1 <= 0
 target_reward_visit_0_50_agent1: - y_50_agent1 + z_0_50_agent1 <= 0
 target_reward_visit_1_50_agent1: - y_50_agent1 + z_1_50_agent1 <= 0
 target_reward_visit_2_50_agent1: - y_50_agent1 + z_2_50_agent1 <= 0
 target_reward_visit_3_50_agent1: - y_50_agent1 + z_3_50_agent1 <= 0
 target_reward_visit_0_51_agent1: - y_51_agent1 + z_0_51_agent1 <= 0
 target_reward_visit_1_51_agent1: - y_51_agent1 + z_1_51_agent1 <= 0
 target_reward_visit_2_51_agent1: - y_51_agent1 + z_2_51_agent1 <= 0
 target_reward_visit_3_51_agent1: - y_51_agent1 + z_3_51_agent1 <= 0
 target_reward_visit_0_52_agent1: - y_52_agent1 + z_0_52_agent1 <= 0
 target_reward_visit_1_52_agent1: - y_52_agent1 + z_1_52_agent1 <= 0
 target_reward_visit_2_52_agent1: - y_52_agent1 + z_2_52_agent1 <= 0
 target_reward_visit_3_52_agent1: - y_52_agent1 + z_3_52_agent1 <= 0
 target_reward_visit_0_53_agent1: - y_53_agent1 + z_0_53_agent1 <= 0
 target_reward_visit_1_53_agent1: - y_53_agent1 + z_1_53_agent1 <= 0
 target_reward_visit_2_53_agent1: - y_53_agent1 + z_2_53_agent1 <= 0
 target_reward_visit_3_53_agent1: - y_53_agent1 + z_3_53_agent1 <= 0
 target_reward_visit_0_54_agent1: - y_54_agent1 + z_0_54_agent1 <= 0
 target_reward_visit_1_54_agent1: - y_54_agent1 + z_1_54_agent1 <= 0
 target_reward_visit_2_54_agent1: - y_54_agent1 + z_2_54_agent1 <= 0
 target_reward_visit_3_54_agent1: - y_54_agent1 + z_3_54_agent1 <= 0
 target_reward_visit_0_55_agent1: - y_55_agent1 + z_0_55_agent1 <= 0
 target_reward_visit_1_55_agent1: - y_55_agent1 + z_1_55_agent1 <= 0
 target_reward_visit_2_55_agent1: - y_55_agent1 + z_2_55_agent1 <= 0
 target_reward_visit_3_55_agent1: - y_55_agent1 + z_3_55_agent1 <= 0
 target_reward_visit_0_56_agent1: - y_56_agent1 + z_0_56_agent1 <= 0
 target_reward_visit_1_56_agent1: - y_56_agent1 + z_1_56_agent1 <= 0
 target_reward_visit_2_56_agent1: - y_56_agent1 + z_2_56_agent1 <= 0
 target_reward_visit_3_56_agent1: - y_56_agent1 + z_3_56_agent1 <= 0
 target_reward_visit_0_57_agent1: - y_57_agent1 + z_0_57_agent1 <= 0
 target_reward_visit_1_57_agent1: - y_57_agent1 + z_1_57_agent1 <= 0
 target_reward_visit_2_57_agent1: - y_57_agent1 + z_2_57_agent1 <= 0
 target_reward_visit_3_57_agent1: - y_57_agent1 + z_3_57_agent1 <= 0
 target_reward_visit_0_58_agent1: - y_58_agent1 + z_0_58_agent1 <= 0
 target_reward_visit_1_58_agent1: - y_58_agent1 + z_1_58_agent1 <= 0
 target_reward_visit_2_58_agent1: - y_58_agent1 + z_2_58_agent1 <= 0
 target_reward_visit_3_58_agent1: - y_58_agent1 + z_3_58_agent1 <= 0
 target_reward_visit_0_59_agent1: - y_59_agent1 + z_0_59_agent1 <= 0
 target_reward_visit_1_59_agent1: - y_59_agent1 + z_1_59_agent1 <= 0
 target_reward_visit_2_59_agent1: - y_59_agent1 + z_2_59_agent1 <= 0
 target_reward_visit_3_59_agent1: - y_59_agent1 + z_3_59_agent1 <= 0
 target_reward_visit_0_60_agent1: - y_60_agent1 + z_0_60_agent1 <= 0
 target_reward_visit_1_60_agent1: - y_60_agent1 + z_1_60_agent1 <= 0
 target_reward_visit_2_60_agent1: - y_60_agent1 + z_2_60_agent1 <= 0
 target_reward_visit_3_60_agent1: - y_60_agent1 + z_3_60_agent1 <= 0
 mtz_0_11_agent1: 32 x_0_11_agent1 + u_0_agent1 - u_11_agent1 <= 31
 mtz_0_15_agent1: 32 x_0_15_agent1 + u_0_agent1 - u_15_agent1 <= 31
 mtz_0_18_agent1: 32 x_0_18_agent1 + u_0_agent1 - u_18_agent1 <= 31
 mtz_5_40_agent1: 32 x_5_40_agent1 + u_5_agent1 - u_40_agent1 <= 31
 mtz_6_40_agent1: 32 x_6_40_agent1 + u_6_agent1 - u_40_agent1 <= 31
 mtz_11_0_agent1: 32 x_11_0_agent1 - u_0_agent1 + u_11_agent1 <= 31
 mtz_11_38_agent1: 32 x_11_38_agent1 + u_11_agent1 - u_38_agent1 <= 31
 mtz_14_40_agent1: 32 x_14_40_agent1 + u_14_agent1 - u_40_agent1 <= 31
 mtz_15_0_agent1: 32 x_15_0_agent1 - u_0_agent1 + u_15_agent1 <= 31
 mtz_16_29_agent1: 32 x_16_29_agent1 + u_16_agent1 - u_29_agent1 <= 31
 mtz_16_37_agent1: 32 x_16_37_agent1 + u_16_agent1 - u_37_agent1 <= 31
 mtz_17_40_agent1: 32 x_17_40_agent1 + u_17_agent1 - u_40_agent1 <= 31
 mtz_18_0_agent1: 32 x_18_0_agent1 - u_0_agent1 + u_18_agent1 <= 31
 mtz_19_40_agent1: 32 x_19_40_agent1 + u_19_agent1 - u_40_agent1 <= 31
 mtz_25_37_agent1: 32 x_25_37_agent1 + u_25_agent1 - u_37_agent1 <= 31
 mtz_25_39_agent1: 32 x_25_39_agent1 + u_25_agent1 - u_39_agent1 <= 31
 mtz_27_39_agent1: 32 x_27_39_agent1 + u_27_agent1 - u_39_agent1 <= 31
 mtz_29_16_agent1: 32 x_29_16_agent1 - u_16_agent1 + u_29_agent1 <= 31
 mtz_29_37_agent1: 32 x_29_37_agent1 + u_29_agent1 - u_37_agent1 <= 31
 mtz_29_39_agent1: 32 x_29_39_agent1 + u_29_agent1 - u_39_agent1 <= 31
 mtz_35_39_agent1: 32 x_35_39_agent1 + u_35_agent1 - u_39_agent1 <= 31
 mtz_35_57_agent1: 32 x_35_57_agent1 + u_35_agent1 - u_57_agent1 <= 31
 mtz_36_38_agent1: 32 x_36_38_agent1 + u_36_agent1 - u_38_agent1 <= 31
 mtz_36_40_agent1: 32 x_36_40_agent1 + u_36_agent1 - u_40_agent1 <= 31
 mtz_37_16_agent1: 32 x_37_16_agent1 - u_16_agent1 + u_37_agent1 <= 31
 mtz_37_25_agent1: 32 x_37_25_agent1 - u_25_agent1 + u_37_agent1 <= 31
 mtz_37_29_agent1: 32 x_37_29_agent1 - u_29_agent1 + u_37_agent1 <= 31
 mtz_37_39_agent1: 32 x_37_39_agent1 + u_37_agent1 - u_39_agent1 <= 31
 mtz_38_11_agent1: 32 x_38_11_agent1 - u_11_agent1 + u_38_agent1 <= 31
 mtz_38_36_agent1: 32 x_38_36_agent1 - u_36_agent1 + u_38_agent1 <= 31
 mtz_38_40_agent1: 32 x_38_40_agent1 + u_38_agent1 - u_40_agent1 <= 31
 mtz_39_25_agent1: 32 x_39_25_agent1 - u_25_agent1 + u_39_agent1 <= 31
 mtz_39_27_agent1: 32 x_39_27_agent1 - u_27_agent1 + u_39_agent1 <= 31
 mtz_39_29_agent1: 32 x_39_29_agent1 - u_29_agent1 + u_39_agent1 <= 31
 mtz_39_35_agent1: 32 x_39_35_agent1 - u_35_agent1 + u_39_agent1 <= 31
 mtz_39_37_agent1: 32 x_39_37_agent1 - u_37_agent1 + u_39_agent1 <= 31
 mtz_39_45_agent1: 32 x_39_45_agent1 + u_39_agent1 - u_45_agent1 <= 31
 mtz_40_5_agent1: 32 x_40_5_agent1 - u_5_agent1 + u_40_agent1 <= 31
 mtz_40_6_agent1: 32 x_40_6_agent1 - u_6_agent1 + u_40_agent1 <= 31
 mtz_40_14_agent1: 32 x_40_14_agent1 - u_14_agent1 + u_40_agent1 <= 31
 mtz_40_17_agent1: 32 x_40_17_agent1 - u_17_agent1 + u_40_agent1 <= 31
 mtz_40_19_agent1: 32 x_40_19_agent1 - u_19_agent1 + u_40_agent1 <= 31
 mtz_40_36_agent1: 32 x_40_36_agent1 - u_36_agent1 + u_40_agent1 <= 31
 mtz_40_38_agent1: 32 x_40_38_agent1 - u_38_agent1 + u_40_agent1 <= 31
 mtz_40_48_agent1: 32 x_40_48_agent1 + u_40_agent1 - u_48_agent1 <= 31
 mtz_45_39_agent1: 32 x_45_39_agent1 - u_39_agent1 + u_45_agent1 <= 31
 mtz_48_40_agent1: 32 x_48_40_agent1 - u_40_agent1 + u_48_agent1 <= 31
 mtz_57_35_agent1: 32 x_57_35_agent1 - u_35_agent1 + u_57_agent1 <= 31
 target_reward_positive_0_11_agent0: z_0_11_agent0 = 0
 target_reward_positive_0_0_agent0: z_0_0_agent0 = 0
 target_reward_positive_0_5_agent0: z_0_5_agent0 = 0
 target_reward_positive_0_6_agent0: z_0_6_agent0 = 0
 target_reward_positive_0_14_agent0: z_0_14_agent0 = 0
 target_reward_positive_0_15_agent0: z_0_15_agent0 = 0
 target_reward_positive_0_16_agent0: z_0_16_agent0 = 0
 target_reward_positive_0_17_agent0: z_0_17_agent0 = 0
 target_reward_positive_0_18_agent0: z_0_18_agent0 = 0
 target_reward_positive_0_19_agent0: z_0_19_agent0 = 0
 target_reward_positive_0_25_agent0: z_0_25_agent0 = 0
 target_reward_positive_0_27_agent0: z_0_27_agent0 = 0
 target_reward_positive_0_29_agent0: z_0_29_agent0 = 0
 target_reward_positive_0_35_agent0: z_0_35_agent0 = 0
 target_reward_positive_0_36_agent0: z_0_36_agent0 = 0
 target_reward_positive_0_37_agent0: z_0_37_agent0 = 0
 target_reward_positive_0_38_agent0: z_0_38_agent0 = 0
 target_reward_positive_0_39_agent0: z_0_39_agent0 = 0
 target_reward_positive_0_40_agent0: z_0_40_agent0 = 0
 target_reward_positive_0_45_agent0: z_0_45_agent0 = 0
 target_reward_positive_0_48_agent0: z_0_48_agent0 = 0
 target_reward_positive_0_50_agent0: z_0_50_agent0 = 0
 target_reward_positive_0_51_agent0: z_0_51_agent0 = 0
 target_reward_positive_0_52_agent0: z_0_52_agent0 = 0
 target_reward_positive_0_53_agent0: z_0_53_agent0 = 0
 target_reward_positive_0_54_agent0: z_0_54_agent0 = 0
 target_reward_positive_0_55_agent0: z_0_55_agent0 = 0
 target_reward_positive_0_56_agent0: z_0_56_agent0 = 0
 target_reward_positive_0_57_agent0: z_0_57_agent0 = 0
 target_reward_positive_0_58_agent0: z_0_58_agent0 = 0
 target_reward_positive_0_59_agent0: z_0_59_agent0 = 0
 target_reward_positive_0_60_agent0: z_0_60_agent0 = 0
 target_reward_positive_0_25_agent1: z_0_25_agent1 = 0
 target_reward_positive_0_0_agent1: z_0_0_agent1 = 0
 target_reward_positive_0_5_agent1: z_0_5_agent1 = 0
 target_reward_positive_0_6_agent1: z_0_6_agent1 = 0
 target_reward_positive_0_11_agent1: z_0_11_agent1 = 0
 target_reward_positive_0_14_agent1: z_0_14_agent1 = 0
 target_reward_positive_0_15_agent1: z_0_15_agent1 = 0
 target_reward_positive_0_16_agent1: z_0_16_agent1 = 0
 target_reward_positive_0_17_agent1: z_0_17_agent1 = 0
 target_reward_positive_0_18_agent1: z_0_18_agent1 = 0
 target_reward_positive_0_19_agent1: z_0_19_agent1 = 0
 target_reward_positive_0_27_agent1: z_0_27_agent1 = 0
 target_reward_positive_0_29_agent1: z_0_29_agent1 = 0
 target_reward_positive_0_35_agent1: z_0_35_agent1 = 0
 target_reward_positive_0_36_agent1: z_0_36_agent1 = 0
 target_reward_positive_0_37_agent1: z_0_37_agent1 = 0
 target_reward_positive_0_38_agent1: z_0_38_agent1 = 0
 target_reward_positive_0_39_agent1: z_0_39_agent1 = 0
 target_reward_positive_0_40_agent1: z_0_40_agent1 = 0
 target_reward_positive_0_45_agent1: z_0_45_agent1 = 0
 target_reward_positive_0_48_agent1: z_0_48_agent1 = 0
 target_reward_positive_0_50_agent1: z_0_50_agent1 = 0
 target_reward_positive_0_51_agent1: z_0_51_agent1 = 0
 target_reward_positive_0_52_agent1: z_0_52_agent1 = 0
 target_reward_positive_0_53_agent1: z_0_53_agent1 = 0
 target_reward_positive_0_54_agent1: z_0_54_agent1 = 0
 target_reward_positive_0_55_agent1: z_0_55_agent1 = 0
 target_reward_positive_0_56_agent1: z_0_56_agent1 = 0
 target_reward_positive_0_57_agent1: z_0_57_agent1 = 0
 target_reward_positive_0_58_agent1: z_0_58_agent1 = 0
 target_reward_positive_0_59_agent1: z_0_59_agent1 = 0
 target_reward_positive_0_60_agent1: z_0_60_agent1 = 0
 target_reward_positive_1_29_agent0: z_1_29_agent0 = 0
 target_reward_positive_1_40_agent0: z_1_40_agent0 = 0
 target_reward_positive_1_50_agent0: z_1_50_agent0 = 0
 target_reward_positive_1_51_agent0: z_1_51_agent0 = 0
 target_reward_positive_1_52_agent0: z_1_52_agent0 = 0
 target_reward_positive_1_53_agent0: z_1_53_agent0 = 0
 target_reward_positive_1_54_agent0: z_1_54_agent0 = 0
 target_reward_positive_1_56_agent0: z_1_56_agent0 = 0
 target_reward_positive_1_58_agent0: z_1_58_agent0 = 0
 target_reward_positive_1_59_agent0: z_1_59_agent0 = 0
 target_reward_positive_1_29_agent1: z_1_29_agent1 = 0
 target_reward_positive_1_40_agent1: z_1_40_agent1 = 0
 target_reward_positive_1_50_agent1: z_1_50_agent1 = 0
 target_reward_positive_1_51_agent1: z_1_51_agent1 = 0
 target_reward_positive_1_52_agent1: z_1_52_agent1 = 0
 target_reward_positive_1_53_agent1: z_1_53_agent1 = 0
 target_reward_positive_1_54_agent1: z_1_54_agent1 = 0
 target_reward_positive_1_56_agent1: z_1_56_agent1 = 0
 target_reward_positive_1_58_agent1: z_1_58_agent1 = 0
 target_reward_positive_1_59_agent1: z_1_59_agent1 = 0
 target_reward_positive_2_29_agent0: z_2_29_agent0 = 0
 target_reward_positive_2_40_agent0: z_2_40_agent0 = 0
 target_reward_positive_2_50_agent0: z_2_50_agent0 = 0
 target_reward_positive_2_51_agent0: z_2_51_agent0 = 0
 target_reward_positive_2_52_agent0: z_2_52_agent0 = 0
 target_reward_positive_2_53_agent0: z_2_53_agent0 = 0
 target_reward_positive_2_54_agent0: z_2_54_agent0 = 0
 target_reward_positive_2_56_agent0: z_2_56_agent0 = 0
 target_reward_positive_2_58_agent0: z_2_58_agent0 = 0
 target_reward_positive_2_59_agent0: z_2_59_agent0 = 0
 target_reward_positive_2_29_agent1: z_2_29_agent1 = 0
 target_reward_positive_2_40_agent1: z_2_40_agent1 = 0
 target_reward_positive_2_50_agent1: z_2_50_agent1 = 0
 target_reward_positive_2_51_agent1: z_2_51_agent1 = 0
 target_reward_positive_2_52_agent1: z_2_52_agent1 = 0
 target_reward_positive_2_53_agent1: z_2_53_agent1 = 0
 target_reward_positive_2_54_agent1: z_2_54_agent1 = 0
 target_reward_positive_2_56_agent1: z_2_56_agent1 = 0
 target_reward_positive_2_58_agent1: z_2_58_agent1 = 0
 target_reward_positive_2_59_agent1: z_2_59_agent1 = 0
 target_reward_positive_3_29_agent0: z_3_29_agent0 = 0
 target_reward_positive_3_40_agent0: z_3_40_agent0 = 0
 target_reward_positive_3_50_agent0: z_3_50_agent0 = 0
 target_reward_positive_3_51_agent0: z_3_51_agent0 = 0
 target_reward_positive_3_52_agent0: z_3_52_agent0 = 0
 target_reward_positive_3_53_agent0: z_3_53_agent0 = 0
 target_reward_positive_3_54_agent0: z_3_54_agent0 = 0
 target_reward_positive_3_56_agent0: z_3_56_agent0 = 0
 target_reward_positive_3_58_agent0: z_3_58_agent0 = 0
 target_reward_positive_3_59_agent0: z_3_59_agent0 = 0
 target_reward_positive_3_29_agent1: z_3_29_agent1 = 0
 target_reward_positive_3_40_agent1: z_3_40_agent1 = 0
 target_reward_positive_3_50_agent1: z_3_50_agent1 = 0
 target_reward_positive_3_51_agent1: z_3_51_agent1 = 0
 target_reward_positive_3_52_agent1: z_3_52_agent1 = 0
 target_reward_positive_3_53_agent1: z_3_53_agent1 = 0
 target_reward_positive_3_54_agent1: z_3_54_agent1 = 0
 target_reward_positive_3_56_agent1: z_3_56_agent1 = 0
 target_reward_positive_3_58_agent1: z_3_58_agent1 = 0
 target_reward_positive_3_59_agent1: z_3_59_agent1 = 0
 target_reward_found_0: z_0_11_agent0 + z_0_0_agent0 + z_0_5_agent0
   + z_0_6_agent0 + z_0_14_agent0 + z_0_15_agent0 + z_0_16_agent0
   + z_0_17_agent0 + z_0_18_agent0 + z_0_19_agent0 + z_0_25_agent0
   + z_0_27_agent0 + z_0_29_agent0 + z_0_35_agent0 + z_0_36_agent0
   + z_0_37_agent0 + z_0_38_agent0 + z_0_39_agent0 + z_0_40_agent0
   + z_0_45_agent0 + z_0_48_agent0 + z_0_50_agent0 + z_0_51_agent0
   + z_0_52_agent0 + z_0_53_agent0 + z_0_54_agent0 + z_0_55_agent0
   + z_0_56_agent0 + z_0_57_agent0 + z_0_58_agent0 + z_0_59_agent0
   + z_0_60_agent0 + z_0_25_agent1 + z_0_0_agent1 + z_0_5_agent1
   + z_0_6_agent1 + z_0_11_agent1 + z_0_14_agent1 + z_0_15_agent1
   + z_0_16_agent1 + z_0_17_agent1 + z_0_18_agent1 + z_0_19_agent1
   + z_0_27_agent1 + z_0_29_agent1 + z_0_35_agent1 + z_0_36_agent1
   + z_0_37_agent1 + z_0_38_agent1 + z_0_39_agent1 + z_0_40_agent1
   + z_0_45_agent1 + z_0_48_agent1 + z_0_50_agent1 + z_0_51_agent1
   + z_0_52_agent1 + z_0_53_agent1 + z_0_54_agent1 + z_0_55_agent1
   + z_0_56_agent1 + z_0_57_agent1 + z_0_58_agent1 + z_0_59_agent1
   + z_0_60_agent1 = 0
 target_reward_unique_1: z_1_11_agent0 + z_1_0_agent0 + z_1_5_agent0
   + z_1_6_agent0 + z_1_14_agent0 + z_1_15_agent0 + z_1_16_agent0
   + z_1_17_agent0 + z_1_18_agent0 + z_1_19_agent0 + z_1_25_agent0
   + z_1_27_agent0 + z_1_29_agent0 + z_1_35_agent0 + z_1_36_agent0
   + z_1_37_agent0 + z_1_38_agent0 + z_1_39_agent0 + z_1_40_agent0
   + z_1_45_agent0 + z_1_48_agent0 + z_1_50_agent0 + z_1_51_agent0
   + z_1_52_agent0 + z_1_53_agent0 + z_1_54_agent0 + z_1_55_agent0
   + z_1_56_agent0 + z_1_57_agent0 + z_1_58_agent0 + z_1_59_agent0
   + z_1_60_agent0 + z_1_25_agent1 + z_1_0_agent1 + z_1_5_agent1
   + z_1_6_agent1 + z_1_11_agent1 + z_1_14_agent1 + z_1_15_agent1
   + z_1_16_agent1 + z_1_17_agent1 + z_1_18_agent1 + z_1_19_agent1
   + z_1_27_agent1 + z_1_29_agent1 + z_1_35_agent1 + z_1_36_agent1
   + z_1_37_agent1 + z_1_38_agent1 + z_1_39_agent1 + z_1_40_agent1
   + z_1_45_agent1 + z_1_48_agent1 + z_1_50_agent1 + z_1_51_agent1
   + z_1_52_agent1 + z_1_53_agent1 + z_1_54_agent1 + z_1_55_agent1
   + z_1_56_agent1 + z_1_57_agent1 + z_1_58_agent1 + z_1_59_agent1
   + z_1_60_agent1 = 1
 target_reward_unique_2: z_2_11_agent0 + z_2_0_agent0 + z_2_5_agent0
   + z_2_6_agent0 + z_2_14_agent0 + z_2_15_agent0 + z_2_16_agent0
   + z_2_17_agent0 + z_2_18_agent0 + z_2_19_agent0 + z_2_25_agent0
   + z_2_27_agent0 + z_2_29_agent0 + z_2_35_agent0 + z_2_36_agent0
   + z_2_37_agent0 + z_2_38_agent0 + z_2_39_agent0 + z_2_40_agent0
   + z_2_45_agent0 + z_2_48_agent0 + z_2_50_agent0 + z_2_51_agent0
   + z_2_52_agent0 + z_2_53_agent0 + z_2_54_agent0 + z_2_55_agent0
   + z_2_56_agent0 + z_2_57_agent0 + z_2_58_agent0 + z_2_59_agent0
   + z_2_60_agent0 + z_2_25_agent1 + z_2_0_agent1 + z_2_5_agent1
   + z_2_6_agent1 + z_2_11_agent1 + z_2_14_agent1 + z_2_15_agent1
   + z_2_16_agent1 + z_2_17_agent1 + z_2_18_agent1 + z_2_19_agent1
   + z_2_27_agent1 + z_2_29_agent1 + z_2_35_agent1 + z_2_36_agent1
   + z_2_37_agent1 + z_2_38_agent1 + z_2_39_agent1 + z_2_40_agent1
   + z_2_45_agent1 + z_2_48_agent1 + z_2_50_agent1 + z_2_51_agent1
   + z_2_52_agent1 + z_2_53_agent1 + z_2_54_agent1 + z_2_55_agent1
   + z_2_56_agent1 + z_2_57_agent1 + z_2_58_agent1 + z_2_59_agent1
   + z_2_60_agent1 = 1
 target_reward_unique_3: z_3_11_agent0 + z_3_0_agent0 + z_3_5_agent0
   + z_3_6_agent0 + z_3_14_agent0 + z_3_15_agent0 + z_3_16_agent0
   + z_3_17_agent0 + z_3_18_agent0 + z_3_19_agent0 + z_3_25_agent0
   + z_3_27_agent0 + z_3_29_agent0 + z_3_35_agent0 + z_3_36_agent0
   + z_3_37_agent0 + z_3_38_agent0 + z_3_39_agent0 + z_3_40_agent0
   + z_3_45_agent0 + z_3_48_agent0 + z_3_50_agent0 + z_3_51_agent0
   + z_3_52_agent0 + z_3_53_agent0 + z_3_54_agent0 + z_3_55_agent0
   + z_3_56_agent0 + z_3_57_agent0 + z_3_58_agent0 + z_3_59_agent0
   + z_3_60_agent0 + z_3_25_agent1 + z_3_0_agent1 + z_3_5_agent1
   + z_3_6_agent1 + z_3_11_agent1 + z_3_14_agent1 + z_3_15_agent1
   + z_3_16_agent1 + z_3_17_agent1 + z_3_18_agent1 + z_3_19_agent1
   + z_3_27_agent1 + z_3_29_agent1 + z_3_35_agent1 + z_3_36_agent1
   + z_3_37_agent1 + z_3_38_agent1 + z_3_39_agent1 + z_3_40_agent1
   + z_3_45_agent1 + z_3_48_agent1 + z_3_50_agent1 + z_3_51_agent1
   + z_3_52_agent1 + z_3_53_agent1 + z_3_54_agent1 + z_3_55_agent1
   + z_3_56_agent1 + z_3_57_agent1 + z_3_58_agent1 + z_3_59_agent1
   + z_3_60_agent1 = 1
 target_directed_agent_assignment_agent0: z_1_11_agent0 + z_2_11_agent0
   + z_3_11_agent0 + z_1_0_agent0 + z_2_0_agent0 + z_3_0_agent0
   + z_1_5_agent0 + z_2_5_agent0 + z_3_5_agent0 + z_1_6_agent0
   + z_2_6_agent0 + z_3_6_agent0 + z_1_14_agent0 + z_2_14_agent0
   + z_3_14_agent0 + z_1_15_agent0 + z_2_15_agent0 + z_3_15_agent0
   + z_1_16_agent0 + z_2_16_agent0 + z_3_16_agent0 + z_1_17_agent0
   + z_2_17_agent0 + z_3_17_agent0 + z_1_18_agent0 + z_2_18_agent0
   + z_3_18_agent0 + z_1_19_agent0 + z_2_19_agent0 + z_3_19_agent0
   + z_1_25_agent0 + z_2_25_agent0 + z_3_25_agent0 + z_1_27_agent0
   + z_2_27_agent0 + z_3_27_agent0 + z_1_29_agent0 + z_2_29_agent0
   + z_3_29_agent0 + z_1_35_agent0 + z_2_35_agent0 + z_3_35_agent0
   + z_1_36_agent0 + z_2_36_agent0 + z_3_36_agent0 + z_1_37_agent0
   + z_2_37_agent0 + z_3_37_agent0 + z_1_38_agent0 + z_2_38_agent0
   + z_3_38_agent0 + z_1_39_agent0 + z_2_39_agent0 + z_3_39_agent0
   + z_1_40_agent0 + z_2_40_agent0 + z_3_40_agent0 + z_1_45_agent0
   + z_2_45_agent0 + z_3_45_agent0 + z_1_48_agent0 + z_2_48_agent0
   + z_3_48_agent0 + z_1_50_agent0 + z_2_50_agent0 + z_3_50_agent0
   + z_1_51_agent0 + z_2_51_agent0 + z_3_51_agent0 + z_1_52_agent0
   + z_2_52_agent0 + z_3_52_agent0 + z_1_53_agent0 + z_2_53_agent0
   + z_3_53_agent0 + z_1_54_agent0 + z_2_54_agent0 + z_3_54_agent0
   + z_1_55_agent0 + z_2_55_agent0 + z_3_55_agent0 + z_1_56_agent0
   + z_2_56_agent0 + z_3_56_agent0 + z_1_57_agent0 + z_2_57_agent0
   + z_3_57_agent0 + z_1_58_agent0 + z_2_58_agent0 + z_3_58_agent0
   + z_1_59_agent0 + z_2_59_agent0 + z_3_59_agent0 + z_1_60_agent0
   + z_2_60_agent0 + z_3_60_agent0 >= 1
 target_directed_agent_assignment_agent1: z_1_25_agent1 + z_2_25_agent1
   + z_3_25_agent1 + z_1_0_agent1 + z_2_0_agent1 + z_3_0_agent1
   + z_1_5_agent1 + z_2_5_agent1 + z_3_5_agent1 + z_1_6_agent1
   + z_2_6_agent1 + z_3_6_agent1 + z_1_11_agent1 + z_2_11_agent1
   + z_3_11_agent1 + z_1_14_agent1 + z_2_14_agent1 + z_3_14_agent1
   + z_1_15_agent1 + z_2_15_agent1 + z_3_15_agent1 + z_1_16_agent1
   + z_2_16_agent1 + z_3_16_agent1 + z_1_17_agent1 + z_2_17_agent1
   + z_3_17_agent1 + z_1_18_agent1 + z_2_18_agent1 + z_3_18_agent1
   + z_1_19_agent1 + z_2_19_agent1 + z_3_19_agent1 + z_1_27_agent1
   + z_2_27_agent1 + z_3_27_agent1 + z_1_29_agent1 + z_2_29_agent1
   + z_3_29_agent1 + z_1_35_agent1 + z_2_35_agent1 + z_3_35_agent1
   + z_1_36_agent1 + z_2_36_agent1 + z_3_36_agent1 + z_1_37_agent1
   + z_2_37_agent1 + z_3_37_agent1 + z_1_38_agent1 + z_2_38_agent1
   + z_3_38_agent1 + z_1_39_agent1 + z_2_39_agent1 + z_3_39_agent1
   + z_1_40_agent1 + z_2_40_agent1 + z_3_40_agent1 + z_1_45_agent1
   + z_2_45_agent1 + z_3_45_agent1 + z_1_48_agent1 + z_2_48_agent1
   + z_3_48_agent1 + z_1_50_agent1 + z_2_50_agent1 + z_3_50_agent1
   + z_1_51_agent1 + z_2_51_agent1 + z_3_51_agent1 + z_1_52_agent1
   + z_2_52_agent1 + z_3_52_agent1 + z_1_53_agent1 + z_2_53_agent1
   + z_3_53_agent1 + z_1_54_agent1 + z_2_54_agent1 + z_3_54_agent1
   + z_1_55_agent1 + z_2_55_agent1 + z_3_55_agent1 + z_1_56_agent1
   + z_2_56_agent1 + z_3_56_agent1 + z_1_57_agent1 + z_2_57_agent1
   + z_3_57_agent1 + z_1_58_agent1 + z_2_58_agent1 + z_3_58_agent1
   + z_1_59_agent1 + z_2_59_agent1 + z_3_59_agent1 + z_1_60_agent1
   + z_2_60_agent1 + z_3_60_agent1 >= 1
 unique_action_agent0_agent1_0: x_11_0_agent0 <= 1
 unique_action_agent0_agent1_5: <= 1
 unique_action_agent0_agent1_6: <= 1
 unique_action_agent0_agent1_11: <= 1
 unique_action_agent0_agent1_14: <= 1
 unique_action_agent0_agent1_15: <= 1
 unique_action_agent0_agent1_16: <= 1
 unique_action_agent0_agent1_17: <= 1
 unique_action_agent0_agent1_18: <= 1
 unique_action_agent0_agent1_19: <= 1
 unique_action_agent0_agent1_25: <= 1
 unique_action_agent0_agent1_27: <= 1
 unique_action_agent0_agent1_29: <= 1
 unique_action_agent0_agent1_35: <= 1
 unique_action_agent0_agent1_36: <= 1
 unique_action_agent0_agent1_37: x_25_37_agent1 <= 1
 unique_action_agent0_agent1_38: x_11_38_agent0 <= 1
 unique_action_agent0_agent1_39: x_25_39_agent1 <= 1
 unique_action_agent0_agent1_40: <= 1
 unique_action_agent0_agent1_45: <= 1
 unique_action_agent0_agent1_48: <= 1
Bounds
 1 <= u_0_agent0 <= 32
 1 <= u_5_agent0 <= 32
 1 <= u_6_agent0 <= 32
 1 <= u_11_agent0 <= 32
 1 <= u_14_agent0 <= 32
 1 <= u_15_agent0 <= 32
 1 <= u_16_agent0 <= 32
 1 <= u_17_agent0 <= 32
 1 <= u_18_agent0 <= 32
 1 <= u_19_agent0 <= 32
 1 <= u_25_agent0 <= 32
 1 <= u_27_agent0 <= 32
 1 <= u_29_agent0 <= 32
 1 <= u_35_agent0 <= 32
 1 <= u_36_agent0 <= 32
 1 <= u_37_agent0 <= 32
 1 <= u_38_agent0 <= 32
 1 <= u_39_agent0 <= 32
 1 <= u_40_agent0 <= 32
 1 <= u_45_agent0 <= 32
 1 <= u_48_agent0 <= 32
 1 <= u_50_agent0 <= 32
 1 <= u_51_agent0 <= 32
 1 <= u_52_agent0 <= 32
 1 <= u_53_agent0 <= 32
 1 <= u_54_agent0 <= 32
 1 <= u_55_agent0 <= 32
 1 <= u_56_agent0 <= 32
 1 <= u_57_agent0 <= 32
 1 <= u_58_agent0 <= 32
 1 <= u_59_agent0 <= 32
 1 <= u_60_agent0 <= 32
 1 <= u_0_agent1 <= 32
 1 <= u_5_agent1 <= 32
 1 <= u_6_agent1 <= 32
 1 <= u_11_agent1 <= 32
 1 <= u_14_agent1 <= 32
 1 <= u_15_agent1 <= 32
 1 <= u_16_agent1 <= 32
 1 <= u_17_agent1 <= 32
 1 <= u_18_agent1 <= 32
 1 <= u_19_agent1 <= 32
 1 <= u_25_agent1 <= 32
 1 <= u_27_agent1 <= 32
 1 <= u_29_agent1 <= 32
 1 <= u_35_agent1 <= 32
 1 <= u_36_agent1 <= 32
 1 <= u_37_agent1 <= 32
 1 <= u_38_agent1 <= 32
 1 <= u_39_agent1 <= 32
 1 <= u_40_agent1 <= 32
 1 <= u_45_agent1 <= 32
 1 <= u_48_agent1 <= 32
 1 <= u_50_agent1 <= 32
 1 <= u_51_agent1 <= 32
 1 <= u_52_agent1 <= 32
 1 <= u_53_agent1 <= 32
 1 <= u_54_agent1 <= 32
 1 <= u_55_agent1 <= 32
 1 <= u_56_agent1 <= 32
 1 <= u_57_agent1 <= 32
 1 <= u_58_agent1 <= 32
 1 <= u_59_agent1 <= 32
 1 <= u_60_agent1 <= 32
 Constant1 = 1
Binaries
 x_0_11_agent0 x_0_15_agent0 x_0_18_agent0 x_5_40_agent0 x_6_40_agent0
 x_11_0_agent0 x_11_38_agent0 x_14_40_agent0 x_15_0_agent0 x_16_29_agent0
 x_16_37_agent0 x_17_40_agent0 x_18_0_agent0 x_19_40_agent0 x_25_37_agent0
 x_25_39_agent0 x_27_39_agent0 x_29_16_agent0 x_29_37_agent0 x_29_39_agent0
 x_35_39_agent0 x_35_57_agent0 x_36_38_agent0 x_36_40_agent0 x_37_16_agent0
 x_37_25_agent0 x_37_29_agent0 x_37_39_agent0 x_38_11_agent0 x_38_36_agent0
 x_38_40_agent0 x_39_25_agent0 x_39_27_agent0 x_39_29_agent0 x_39_35_agent0
 x_39_37_agent0 x_39_45_agent0 x_40_5_agent0 x_40_6_agent0 x_40_14_agent0
 x_40_17_agent0 x_40_19_agent0 x_40_36_agent0 x_40_38_agent0 x_40_48_agent0
 x_45_39_agent0 x_48_40_agent0 x_57_35_agent0 x_0_11_agent1 x_0_15_agent1
 x_0_18_agent1 x_5_40_agent1 x_6_40_agent1 x_11_0_agent1 x_11_38_agent1
 x_14_40_agent1 x_15_0_agent1 x_16_29_agent1 x_16_37_agent1 x_17_40_agent1
 x_18_0_agent1 x_19_40_agent1 x_25_37_agent1 x_25_39_agent1 x_27_39_agent1
 x_29_16_agent1 x_29_37_agent1 x_29_39_agent1 x_35_39_agent1 x_35_57_agent1
 x_36_38_agent1 x_36_40_agent1 x_37_16_agent1 x_37_25_agent1 x_37_29_agent1
 x_37_39_agent1 x_38_11_agent1 x_38_36_agent1 x_38_40_agent1 x_39_25_agent1
 x_39_27_agent1 x_39_29_agent1 x_39_35_agent1 x_39_37_agent1 x_39_45_agent1
 x_40_5_agent1 x_40_6_agent1 x_40_14_agent1 x_40_17_agent1 x_40_19_agent1
 x_40_36_agent1 x_40_38_agent1 x_40_48_agent1 x_45_39_agent1 x_48_40_agent1
 x_57_35_agent1 y_0_agent0 y_5_agent0 y_6_agent0 y_14_agent0 y_15_agent0
 y_16_agent0 y_17_agent0 y_18_agent0 y_19_agent0 y_25_agent0 y_27_agent0
 y_29_agent0 y_35_agent0 y_36_agent0 y_37_agent0 y_38_agent0 y_39_agent0
 y_40_agent0 y_45_agent0 y_48_agent0 y_50_agent0 y_51_agent0 y_52_agent0
 y_53_agent0 y_54_agent0 y_55_agent0 y_56_agent0 y_57_agent0 y_58_agent0
 y_59_agent0 y_60_agent0 y_0_agent1 y_5_agent1 y_6_agent1 y_11_agent1
 y_14_agent1 y_15_agent1 y_16_agent1 y_17_agent1 y_18_agent1 y_19_agent1
 y_27_agent1 y_29_agent1 y_35_agent1 y_36_agent1 y_37_agent1 y_38_agent1
 y_39_agent1 y_40_agent1 y_45_agent1 y_48_agent1 y_50_agent1 y_51_agent1
 y_52_agent1 y_53_agent1 y_54_agent1 y_55_agent1 y_56_agent1 y_57_agent1
 y_58_agent1 y_59_agent1 y_60_agent1 z_0_11_agent0 z_1_11_agent0
 z_2_11_agent0 z_3_11_agent0 z_0_0_agent0 z_1_0_agent0 z_2_0_agent0
 z_3_0_agent0 z_0_5_agent0 z_1_5_agent0 z_2_5_agent0 z_3_5_agent0
 z_0_6_agent0 z_1_6_agent0 z_2_6_agent0 z_3_6_agent0 z_0_14_agent0
 z_1_14_agent0 z_2_14_agent0 z_3_14_agent0 z_0_15_agent0 z_1_15_agent0
 z_2_15_agent0 z_3_15_agent0 z_0_16_agent0 z_1_16_agent0 z_2_16_agent0
 z_3_16_agent0 z_0_17_agent0 z_1_17_agent0 z_2_17_agent0 z_3_17_agent0
 z_0_18_agent0 z_1_18_agent0 z_2_18_agent0 z_3_18_agent0 z_0_19_agent0
 z_1_19_agent0 z_2_19_agent0 z_3_19_agent0 z_0_25_agent0 z_1_25_agent0
 z_2_25_agent0 z_3_25_agent0 z_0_27_agent0 z_1_27_agent0 z_2_27_agent0
 z_3_27_agent0 z_0_29_agent0 z_1_29_agent0 z_2_29_agent0 z_3_29_agent0
 z_0_35_agent0 z_1_35_agent0 z_2_35_agent0 z_3_35_agent0 z_0_36_agent0
 z_1_36_agent0 z_2_36_agent0 z_3_36_agent0 z_0_37_agent0 z_1_37_agent0
 z_2_37_agent0 z_3_37_agent0 z_0_38_agent0 z_1_38_agent0 z_2_38_agent0
 z_3_38_agent0 z_0_39_agent0 z_1_39_agent0 z_2_39_agent0 z_3_39_agent0
 z_0_40_agent0 z_1_40_agent0 z_2_40_agent0 z_3_40_agent0 z_0_45_agent0
 z_1_45_agent0 z_2_45_agent0 z_3_45_agent0 z_0_48_agent0 z_1_48_agent0
 z_2_48_agent0 z_3_48_agent0 z_0_50_agent0 z_1_50_agent0 z_2_50_agent0
 z_3_50_agent0 z_0_51_agent0 z_1_51_agent0 z_2_51_agent0 z_3_51_agent0
 z_0_52_agent0 z_1_52_agent0 z_2_52_agent0 z_3_52_agent0 z_0_53_agent0
 z_1_53_agent0 z_2_53_agent0 z_3_53_agent0 z_0_54_agent0 z_1_54_agent0
 z_2_54_agent0 z_3_54_agent0 z_0_55_agent0 z_1_55_agent0 z_2_55_agent0
 z_3_55_agent0 z_0_56_agent0 z_1_56_agent0 z_2_56_agent0 z_3_56_agent0
 z_0_57_agent0 z_1_57_agent0 z_2_57_agent0 z_3_57_agent0 z_0_58_agent0
 z_1_58_agent0 z_2_58_agent0 z_3_58_agent0 z_0_59_agent0 z_1_59_agent0
 z_2_59_agent0 z_3_59_agent0 z_0_60_agent0 z_1_60_agent0 z_2_60_agent0
 z_3_60_agent0 z_0_25_agent1 z_1_25_agent1 z_2_25_agent1 z_3_25_agent1
 z_0_0_agent1 z_1_0_agent1 z_2_0_agent1 z_3_0_agent1 z_0_5_agent1
 z_1_5_agent1 z_2_5_agent1 z_3_5_agent1 z_0_6_agent1 z_1_6_agent1
 z_2_6_agent1 z_3_6_agent1 z_0_11_agent1 z_1_11_agent1 z_2_11_agent1
 z_3_11_agent1 z_0_14_agent1 z_1_14_agent1 z_2_14_agent1 z_3_14_agent1
 z_0_15_agent1 z_1_15_agent1 z_2_15_agent1 z_3_15_agent1 z_0_16_agent1
 z_1_16_agent1 z_2_16_agent1 z_3_16_agent1 z_0_17_agent1 z_1_17_agent1
 z_2_17_agent1 z_3_17_agent1 z_0_18_agent1 z_1_18_agent1 z_2_18_agent1
 z_3_18_agent1 z_0_19_agent1 z_1_19_agent1 z_2_19_agent1 z_3_19_agent1
 z_0_27_agent1 z_1_27_agent1 z_2_27_agent1 z_3_27_agent1 z_0_29_agent1
 z_1_29_agent1 z_2_29_agent1 z_3_29_agent1 z_0_35_agent1 z_1_35_agent1
 z_2_35_agent1 z_3_35_agent1 z_0_36_agent1 z_1_36_agent1 z_2_36_agent1
 z_3_36_agent1 z_0_37_agent1 z_1_37_agent1 z_2_37_agent1 z_3_37_agent1
 z_0_38_agent1 z_1_38_agent1 z_2_38_agent1 z_3_38_agent1 z_0_39_agent1
 z_1_39_agent1 z_2_39_agent1 z_3_39_agent1 z_0_40_agent1 z_1_40_agent1
 z_2_40_agent1 z_3_40_agent1 z_0_45_agent1 z_1_45_agent1 z_2_45_agent1
 z_3_45_agent1 z_0_48_agent1 z_1_48_agent1 z_2_48_agent1 z_3_48_agent1
 z_0_50_agent1 z_1_50_agent1 z_2_50_agent1 z_3_50_agent1 z_0_51_agent1
 z_1_51_agent1 z_2_51_agent1 z_3_51_agent1 z_0_52_agent1 z_1_52_agent1
 z_2_52_agent1 z_3_52_agent1 z_0_53_agent1 z_1_53_agent1 z_2_53_agent1
 z_3_53_agent1 z_0_54_agent1 z_1_54_agent1 z_2_54_agent1 z_3_54_agent1
 z_0_55_agent1 z_1_55_agent1 z_2_55_agent1 z_3_55_agent1 z_0_56_agent1
 z_1_56_agent1 z_2_56_agent1 z_3_56_agent1 z_0_57_agent1 z_1_57_agent1
 z_2_57_agent1 z_3_57_agent1 z_0_58_agent1 z_1_58_agent1 z_2_58_agent1
 z_3_58_agent1 z_0_59_agent1 z_1_59_agent1 z_2_59_agent1 z_3_59_agent1
 z_0_60_agent1 z_1_60_agent1 z_2_60_agent1 z_3_60_agent1
End
