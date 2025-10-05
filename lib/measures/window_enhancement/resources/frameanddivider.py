            # NOT IN USE, switch to use window type subsurface area and gwp_per_m2 to calculate embodied carbon of window frame
            # get frame and divider dimensions:
            # reference: https://bigladdersoftware.com/epx/docs/9-3/input-output-reference/group-thermal-zone-description-geometry.html#windowpropertyframeanddivider
            # if subsurface.windowPropertyFrameAndDivider().is_initialized(): # check if frame_and_divider exist in selected subsurface
            #     frame = subsurface.windowPropertyFrameAndDivider().get()
            #     frame_name = frame.nameString()
            #     frame_width = frame.frameWidth()
            #     frame_op = frame.frameOutsideProjection()
            #     frame_ip = frame.frameInsideProjection()
            #     frame_cross_section_area = frame_width * (frame_op + frame_ip + subsurface_dict[subsurface_name]["Glass"]["Total thickness (m)"]) #revise thickness
            #     frame_perimeter = subsurface_dict[subsurface_name]["dimension"]["perimeter"]

            #     if frame.numberOfHorizontalDividers() != 0 or frame.numberOfVerticalDividers() != 0:
            #         divider_width = frame.dividerWidth()
            #         divider_op = frame.dividerOutsideProjection()
            #         divider_ip = frame.dividerInsideProjection()
            #         divider_cross_section_area = divider_width * (divider_op + divider_ip + subsurface_dict[subsurface_name]["Glass"]["Total thickness (m)"]) #revise thickness
            #         num_hori_divider = frame.numberOfHorizontalDividers() # integer
            #         num_verti_divider = frame.numberOfVerticalDividers() # integer
            #         total_divider_length = (num_hori_divider * subsurface_dict[subsurface_name]["dimension"]["width"] +
            #                                  num_verti_divider * subsurface_dict[subsurface_name]["dimension"]["length"])
            #     else:
            #         divider_width = 0.0
            #         divider_cross_section_area = 0.0
            #         runner.registerInfo(f"In {subsurface.nameString()}'s Frame {frame_name}: no divider")

            #     runner.registerInfo(f"In {subsurface.nameString()}'s Frame and divider: {frame_name},"
            #                         f"Frame Width: {frame_width} m, cross sectional area: {frame_cross_section_area} m2, perimeter: {frame_perimeter}"
            #                         f"Divider width: {divider_width}m, cross sectional area: {divider_cross_section_area} m2, total length: {total_divider_length} m")
            # else:
            #     runner.registerInfo(f"In {subsurface.nameString()}: no frame and divider")

            # subsurface_dict[subsurface_name]["Frame"]["Object"] = frame
            # subsurface_dict[subsurface_name]["Frame"]["Frame cross sectional area (m2)"] = frame_cross_section_area
            # subsurface_dict[subsurface_name]["Frame"]["Divider cross sectional area (m2)"] = divider_cross_section_area
            # subsurface_dict[subsurface_name]["Frame"]["Volume (m3)"] = frame_cross_section_area * frame_perimeter + divider_cross_section_area * total_divider_length

            # # get thickness from each window construction layer
            # total_glass_thickness = 0.0
            # for i in range(layered_construction.numLayers()):
            #     material = layered_construction.getLayer(i)
            #     runner.registerInfo(f"Layer {i+1}: {material.nameString()}") 
            #     if material.thickness(): # count air layer thickness (delete: and "Air" not in material.nameString():)
            #         glass_thickness = material.thickness()
            #         runner.registerInfo(f"In {subsurface_name}: Material: {material.nameString()}, Thickness: {glass_thickness} m")
            #         total_glass_thickness += glass_thickness
            #     else: # handle the case when no thickness is prodvied by the model 
            #         glass_thickness = 0.003
            #         total_glass_thickness += glass_thickness
            #         runner.registerInfo(f"In {subsurface_name}: Material: {material.nameString()} doesn't have thickness attribute and a default thickness of 3 mm assigned.")
            #subsurface_dict[subsurface_name]["Glass"]["Total thickness (m)"] = total_glass_thickness
            #subsurface_dict[subsurface_name]["Glass"]["Volume (m3)"] = total_glass_thickness * glass_area