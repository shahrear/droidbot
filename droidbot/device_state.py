import os
import math
import subprocess
from input_event import KeyEvent, IntentEvent, TouchEvent, LongTouchEvent, SwipeEvent, ScrollEvent


class DeviceState(object):
    """
    the state of the current device
    """

    def __init__(self, device, views, foreground_activity, activity_stack, background_services,
                 tag=None, screenshot_path=None):
        self.device = device
        self.foreground_activity = foreground_activity
        self.activity_stack = activity_stack
        self.background_services = background_services
        if tag is None:
            from datetime import datetime
            tag = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        self.tag = tag
        self.screenshot_path = screenshot_path
        self.views = DeviceState.__parse_views(views)
        self.__generate_view_strs()
        self.state_str = self.__get_state_str()

    def to_dict(self):
        state = {'tag': self.tag,
                 'state_str': self.state_str,
                 'foreground_activity': self.foreground_activity,
                 'activity_stack': self.activity_stack,
                 'background_services': self.background_services,
                 'views': self.views}
        return state

    def to_json(self):
        import json
        return json.dumps(self.to_dict(), indent=2)

    @staticmethod
    def __parse_views(raw_views):
        views = []
        if not raw_views or len(raw_views) == 0:
            return views

        from adapter.viewclient import View
        if isinstance(raw_views[0], View):  # If the raw views are from viewclient
            view2id_map = {}
            id2view_map = {}
            temp_id = 0
            for view in raw_views:
                view2id_map[view] = temp_id
                id2view_map[temp_id] = view
                temp_id += 1

            for view in raw_views:
                view_dict = {}
                view_dict['class'] = view.getClass()  # None is possible value
                view_dict['text'] = view.getText()  # None is possible value
                view_dict['resource_id'] = view.getId()  # None is possible value

                view_dict['parent'] = DeviceState.__safe_dict_get(view2id_map, view.getParent(), -1)
                view_dict['temp_id'] = view2id_map.get(view)

                view_dict['children'] = [view2id_map.get(view_child) for view_child in view.getChildren()]
                view_dict['enabled'] = view.isEnabled()
                view_dict['focused'] = view.isFocused()
                view_dict['clickable'] = view.isClickable()
                view_dict['bounds'] = view.getBounds()
                view_dict['size'] = "%d*%d" % (view.getWidth(), view.getHeight())
                views.append(view_dict)
        elif isinstance(raw_views[0], dict):  # If the raw views are from droidbotApp
            for view_dict in raw_views:
                # # Simplify resource_id
                # resource_id = view_dict['resource_id']
                # if resource_id is not None and ":" in resource_id:
                #     resource_id = resource_id[(resource_id.find(":") + 1):]
                #     view_dict['resource_id'] = resource_id
                views.append(view_dict)
        return views

    def __generate_view_strs(self):
        for view_dict in self.views:
            self.__get_view_str(view_dict)

    @staticmethod
    def __calculate_depth(views):
        root_view = None
        for view in views:
            if DeviceState.__safe_dict_get(view, 'parent') == -1:
                root_view = view
                break
        DeviceState.__assign_depth(views, root_view, 0)

    @staticmethod
    def __assign_depth(views, view_dict, depth):
        view_dict['depth'] = depth
        for view_id in DeviceState.__safe_dict_get(view_dict, 'children', []):
            DeviceState.__assign_depth(views, views[view_id], depth + 1)

    def __get_state_str(self):
        view_strs = set()
        for view in self.views:
            if 'view_str' in view:
                view_str = view['view_str']
                if view_str is not None and len(view_str) > 0:
                    view_strs.add(view_str)
        state_str = "%s{%s}" % (self.foreground_activity, ",".join(sorted(view_strs)))
        import hashlib
        return hashlib.sha256(state_str.encode('utf-8')).hexdigest()

    def save2dir(self, output_dir=None):
        try:
            if output_dir is None:
                if self.device.output_dir is None:
                    return
                else:
                    output_dir = os.path.join(self.device.output_dir, "states")
            if not os.path.exists(output_dir):
                os.mkdir(output_dir)
            state_json_file_path = "%s/state_%s.json" % (output_dir, self.tag)
            screenshot_output_path = "%s/screen_%s.png" % (output_dir, self.tag)
            state_json_file = open(state_json_file_path, "w")
            state_json_file.write(self.to_json())
            state_json_file.close()
            subprocess.check_call(["cp", self.screenshot_path, screenshot_output_path])
            # from PIL.Image import Image
            # if isinstance(self.screenshot_path, Image):
            #     self.screenshot_path.save(screenshot_output_path)
        except Exception as e:
            self.device.logger.warning("saving state to dir failed: " + e.message)

    def is_different_from(self, another_state):
        """
        compare this state with another
        @param another_state: DeviceState
        @return: boolean, true if this state is different from other_state
        """
        return self.state_str != another_state.state_str

    @staticmethod
    def __get_view_signature(view_dict):
        """
        get the signature of the given view
        @param view_dict: dict, an element of list device.get_current_state().views
        @return:
        """
        if 'signature' in view_dict:
            return view_dict['signature']
        signature = "[class]%s[resource_id]%s[text]%s[%s,%s,%s,%s]" % \
                    (DeviceState.__safe_dict_get(view_dict, 'class', "None"),
                     DeviceState.__safe_dict_get(view_dict, 'resource_id', "None"),
                     DeviceState.__safe_dict_get(view_dict, 'text', "None"),
                     DeviceState.__key_if_true(view_dict, 'enabled'),
                     DeviceState.__key_if_true(view_dict, 'checked'),
                     DeviceState.__key_if_true(view_dict, 'selected'),
                     DeviceState.__key_if_true(view_dict, 'focused'))
        view_dict['signature'] = signature
        return signature

    def __get_view_str(self, view_dict):
        """
        get a string which can represent the given view
        @param view_dict: dict, an element of list device.get_current_state().views
        @return:
        """
        if 'view_str' in view_dict:
            return view_dict['view_str']
        view_signature = DeviceState.__get_view_signature(view_dict)
        parent_strs = []
        for parent_id in self.get_all_ancestors(view_dict):
            parent_strs.append(DeviceState.__get_view_signature(self.views[parent_id]))
        parent_strs.reverse()
        view_str = "%s//%s//%s" % (self.foreground_activity, "//".join(parent_strs), view_signature)
        view_dict['view_str'] = view_str
        return view_str

    @staticmethod
    def __key_if_true(view_dict, key):
        return key if (key in view_dict and view_dict[key]) else ""

    @staticmethod
    def __safe_dict_get(view_dict, key, default=None):
        return view_dict[key] if (key in view_dict) else default

    @staticmethod
    def get_view_center(view_dict):
        """
        return the center point in a view
        @param view_dict: dict, element of device.get_current_state().views
        @return:
        """
        bounds = view_dict['bounds']
        return (bounds[0][0] + bounds[1][0]) / 2, (bounds[0][1] + bounds[1][1]) / 2

    @staticmethod
    def get_view_size(view_dict):
        """
        return the size of a view
        @param view_dict: dict, element of device.get_current_state().views
        @return:
        """
        bounds = view_dict['bounds']
        return int(math.fabs((bounds[0][0] - bounds[1][0]) * (bounds[0][1] - bounds[1][1])))

    def get_all_ancestors(self, view_dict):
        result = []
        parent_id = self.__safe_dict_get(view_dict, 'parent', -1)
        if 0 <= parent_id < len(self.views):
            result.append(parent_id)
            result += self.get_all_ancestors(self.views[parent_id])
        return result

    def get_all_children(self, view_dict):
        children = self.__safe_dict_get(view_dict, 'children')
        if not children:
            return set()
        children = set(children)
        for child in children:
            children_of_child = self.get_all_children(self.views[child])
            children.union(children_of_child)
        return children

    def get_possible_input(self):
        """
        Get a list of possible input events for this state
        :return: 
        """
        possible_events = []
        enabled_view_ids = set()
        touch_exclude_view_ids = set()
        for view_dict in self.views:
            if self.__safe_dict_get(view_dict, 'enabled'):
                enabled_view_ids.add(view_dict['temp_id'])

        for view_id in enabled_view_ids:
            if self.__safe_dict_get(self.views[view_id], 'clickable'):
                possible_events.append(TouchEvent(view=self.views[view_id]))
                touch_exclude_view_ids.add(view_id)
                touch_exclude_view_ids.union(self.get_all_children(self.views[view_id]))

        for view_id in enabled_view_ids:
            if self.__safe_dict_get(self.views[view_id], 'scrollable'):
                possible_events.append(ScrollEvent(view=self.views[view_id], direction="UP"))
                possible_events.append(ScrollEvent(view=self.views[view_id], direction="DOWN"))
                possible_events.append(ScrollEvent(view=self.views[view_id], direction="LEFT"))
                possible_events.append(ScrollEvent(view=self.views[view_id], direction="RIGHT"))

        for view_id in enabled_view_ids:
            if self.__safe_dict_get(self.views[view_id], 'checkable'):
                possible_events.append(TouchEvent(view=self.views[view_id]))
                touch_exclude_view_ids.add(view_id)
                touch_exclude_view_ids.union(self.get_all_children(self.views[view_id]))

        for view_id in enabled_view_ids:
            if self.__safe_dict_get(self.views[view_id], 'long_clickable'):
                possible_events.append(LongTouchEvent(view=self.views[view_id]))

        for view_id in enabled_view_ids:
            if self.__safe_dict_get(self.views[view_id], 'editable'):
                touch_exclude_view_ids.add(view_id)
                # TODO figure out what event can be sent to editable views
                pass

        for view_id in enabled_view_ids:
            if view_id in touch_exclude_view_ids:
                continue
            children = self.__safe_dict_get(self.views[view_id], 'children')
            if children and len(children) > 0:
                continue
            possible_events.append(TouchEvent(view=self.views[view_id]))

        return possible_events
