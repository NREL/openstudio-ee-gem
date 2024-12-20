# *******************************************************************************
# OpenStudio(R), Copyright (c) Alliance for Sustainable Energy, LLC.
# See also https://openstudio.net/license
# *******************************************************************************
import typing
import openstudio

# Start the measure

class WindowEnhancment(openstudio.measure.ModelMeasure):
    """A ModelMeasure."""

    def name(self):
        """
        Embodied emissions for window enhancement.
        """
        return "Window Enhancment"

    def description(self):
        """
        Calculate embodied emissions associated with adding film,
        storm window, or something else to an existing building.
        """
        return "Calculate embodied emissions for window enhancements."

    def modeler_description(self):
        """
        Layered construction approach will be used.
        """
        return "Layered construction approach being used."

    # define the arguments that the user will input
    def arguments(self, model: typing.Optional[openstudio.model.Model] = None):
        """Prepares user arguments for the measure.

        Measure arguments define which -- if any -- input parameters the user may set before running the measure.
        """
        args = openstudio.measure.OSArgumentVector()

        # make a choice argument for constructions that are appropriate for windows
        construction_handles = openstudio.StringVector()
        construction_display_names = openstudio.StringVector()

        # putting space types and names into hash
        construction_args = model.getConstructions(model)
        construction_args_hash = {}
        for construction_arg in construction_args:
            construction_args_hash[str(construction_arg.name)] = construction_arg
            print(construction_arg)

        # looping through sorted hash of constructions
        construction_args_hash = dict(sorted(construction_args_hash.items()))
        construction_handles = []
        construction_display_names = []
        for key, value in construction_args_hash.items():
            # only include if construction is a valid fenestration construction
            if value.isFenestration():
                construction_handles.append(str(value.handle))
                construction_display_names.append(key)
        print(construction_handles)
        print(construction_display_names)

        # make a choice argument for fixed windows
        construction = openstudio.measure.OSArgument.makeChoiceArgument("construction", construction_handles, construction_display_names, True)
        construction.setDisplayName("Pick a Window Construction From the Model to Replace Existing Window Constructions.")
        args.append(construction)

        # clone construction to get proper area for measure economics, in case it is used elsewhere in the building
        new_object = construction.clone(model)
        if not new_object.to_Construction().is_empty():
            construction = new_object.to_Construction.get()

        # make a bool argument for fixed windows
        change_fixed_windows = openstudio.measure.OSArgument.makeBoolArgument("change_fixed_windows", True)
        change_fixed_windows.setDisplayName("Change Fixed Windows?")
        change_fixed_windows.setDefaultValue(True)
        args.append(change_fixed_windows)

        # make a bool argument for operable windows
        change_operable_windows = openstudio.measure.OSArgument.makeBoolArgument("change_operable_windows", True)
        change_operable_windows.setDisplayName("Change Operable Windows?")
        change_operable_windows.setDefaultValue(True)
        args.append(change_operable_windows)

        # make an argument carbon intensity of IGU
        ci_igu = openstudio.measure.OSArgument.makeDoubleArgument("ci_igu", True)
        ci_igu.setDisplayName("GWP of IGU in kg CO2 eq per m3")
        ci_igu.setDefaultValue(0.0)
        args.append(ci_igu)

        # make an argument carbon intensity of window frame
        ci_wframe = openstudio.measure.OSArgument.makeDoubleArgument("ci_wframe", True)
        ci_wframe.setDisplayName("GWP of window frame in kg CO2 eq per m3")
        ci_wframe.setDefaultValue(0.0)
        args.append(ci_wframe)

        # make an argument volume of IGU
        vol_igu = openstudio.measure.OSArgument.makeDoubleArgument("vol_igu", True)
        vol_igu.setDisplayName("Volume of IGU in m3")
        vol_igu.setDefaultValue(0.0)
        args.append(vol_igu)

        # make an argument volume of window frame
        vol_wframe = openstudio.measure.OSArgument.makeDoubleArgument("vol_wframe", True)
        vol_wframe.setDisplayName("Volume of window frame in m3")
        vol_wframe.setDefaultValue(0.0)
        args.append(vol_wframe)

        return args

    def run(
        self,
        model: openstudio.model.Model,
        runner: openstudio.measure.OSRunner,
        user_arguments: openstudio.measure.OSArgumentMap,
    ):
        """Defines what happens when the measure is run."""
        super().run(model, runner, user_arguments)  # Do **NOT** remove this line

        if not (runner.validateUserArguments(self.arguments(model), user_arguments)):
            return False

        # assign the user inputs to variables
        ci_igu = runner.getDoubleArgumentValue("ci_igu", user_arguments)
        ci_wframe = runner.getDoubleArgumentValue("ci_wframe", user_arguments)
        vol_igu = runner.getDoubleArgumentValue("vol_igu", user_arguments)
        vol_wframe = runner.getDoubleArgumentValue("vol_wframe", user_arguments)

        # check the ci_igu for reasonableness
        if ci_igu < 0:
            runner.registerError("GWP of IGU can not be zero.")
            return False

        # check the ci_wframe for reasonableness
        if ci_wframe < 0:
            runner.registerError("GWP of window frame can not be zero.")
            return False

        # check the vol_igu for reasonableness
        if vol_igu < 0:
            runner.registerError("Volume of IGU can not be zero.")
            return False

        # check the vol_wframe for reasonableness
        if vol_wframe < 0:
            runner.registerError("Volume of window frame can not be zero.")
            return False

        # report initial condition of model
        runner.registerInitialCondition(f"The building started with {len(model.getSpaces())} spaces.")

        # add a new space to the model
        new_space = openstudio.model.Space(model)
        new_space.setName("space_name")

        # https://openstudio-sdk-documentation.s3.amazonaws.com/cpp/OpenStudio-1.7.0-doc/model/html/classopenstudio_1_1model_1_1_glazing.html
        igu = openstudio.model.Glazing(model)
        igu.setName("IGU")

        # https://openstudio-sdk-documentation.s3.amazonaws.com/cpp/OpenStudio-1.7.0-doc/model/html/classopenstudio_1_1model_1_1_shade.html
        shade = openstudio.model.ShadingMaterial(model)
        shade_thickness = shade.getThickness()

        # https://openstudio-sdk-documentation.s3.amazonaws.com/cpp/OpenStudio-1.7.0-doc/model/html/classopenstudio_1_1model_1_1_window_property_frame_and_divider.html
        wframe = openstudio.model.WindowPropertyFrameAndDivider(model)
        wframe.setFrameWidth(thickness)
        wframe_thickness = wframe.frameWidth()

        # ip construction area for reporting
        '''
        const_area_ip = openstudio.convert(openstudio.Quantity(construction.getNetArea, openstudio.createUnit('m^2').get), openstudio.createUnit('ft^2').get).get.value
        net_area_ft2 = net_area_m2 * 10.7639  # 1 m2 ≈ 10.7639 inch2
        const_area_ip = net_area_ft2
        '''

        # echo the new space's name back to the user
        runner.registerInfo(f"Space {new_space.nameString()} was added.")

        # report final condition of model
        runner.registerFinalCondition(f"The building finished with {len(model.getSpaces())} spaces.")

        return True


# register the measure to be used by the application
WindowEnhancment().registerWithApplication()
